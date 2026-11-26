#!/usr/bin/env python3
"""Our re-implementation of the published privacy attack arena (docs/ATTACKS.md).

Development / demo tool, never part of the pipeline. It runs the same attacks on the **raw
input** and on a **release**, and reports risks the way the scorer does (A1–A5 relative to
raw). Nothing personal is printed: only rates, counts and ratios.

Attacks
    A1 direct exposure     share of patients with a surviving critical identifier / full name
    A2/A3 record linkage   mean probability mass the registry attacker puts on the true person
    A4 profile re-id       share of patients re-identified with confidence ≥ 0.5 after pooling
                           records through in-data pseudonyms and shared reference values
    A5 targeted            success against people with known facts (visit date, hospital,
                           rare condition), after trying to recover a single global date shift
    A6 pseudonym inversion share of pseudonyms equal to / prefixing a transform of originals
    A7 cross-release       (optional, ``--rotated``) share of pseudonyms or shifted dates that
                           are unchanged under a different secret

Usage::

    python tools/attacker.py --release OUT [--rotated OUT2] [--kit KIT | --input IN --truth T --attacker DIR]
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anamika.privacy.dates import find_dates  # noqa: E402
from anamika.translit.keys import name_key, place_key  # noqa: E402
from tools.leak_scan import DEFAULT_KIT, keys_for, normalise, read_norm  # noqa: E402

WEIGHTS = {"A1": 0.20, "A23": 0.20, "A4": 0.20, "A5": 0.20, "A6": 0.10, "A7": 0.10}
PSN = re.compile(r"PSN-[0-9A-Z]{6}")
REF_KEYS = re.compile(r"(?i)patient_?ref|uhid|mrn|reg_?no|hospital_?(?:uhid|no)|pt_?id|patient_?id")
AGE_FORMS = [
    re.compile(r"(?i)(?<![A-Za-z])(?:age(?:\s*/\s*sex)?|umar|आयु|उम्र)\s*[:\-]?\s*(\d{1,3})(?:\s*-\s*(\d{1,3})|\+)?"),
    re.compile(r"(?<![\d.\-])(\d{1,3})(?:\s*-\s*(\d{1,3}))?\s*(?:Yrs?|Years?|Y|yrs?|वर्ष)?\.?\s*/\s*(?:M|F|Male|Female|पुरुष|महिला)\b"),
    re.compile(r"(?:^|,)\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?\s*(?:yrs?|years?)\b", re.I | re.M),
    re.compile(r"(?<![\d.])(\d{1,3})(?:\s*-\s*(\d{1,3}))?\s*वर्ष"),
]
BAND_PLUS = re.compile(r"(?<!\d)(\d{2,3})\+")


# --------------------------------------------------------------------------- evidence

@dataclass
class Ev:
    """What the attacker can read from one record (or a pooled profile)."""

    phones: set[str] = field(default_factory=set)
    masked: set[tuple[str, str]] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    last4: set[str] = field(default_factory=set)
    ages: list[tuple[int, int]] = field(default_factory=list)
    byears: set[int] = field(default_factory=set)
    genders: set[str] = field(default_factory=set)
    districts: set[str] = field(default_factory=set)
    tehsils: set[str] = field(default_factory=set)
    villages: set[str] = field(default_factory=set)
    pins: set[str] = field(default_factory=set)
    pin3: set[str] = field(default_factory=set)
    name_keys: set[str] = field(default_factory=set)
    tokens: set[str] = field(default_factory=set)
    rel_keys: set[str] = field(default_factory=set)
    houses: set[str] = field(default_factory=set)
    dates: set[dt.date] = field(default_factory=set)
    intervals: set[int] = field(default_factory=set)
    conditions: set[str] = field(default_factory=set)
    hospitals: set[str] = field(default_factory=set)
    psns: set[str] = field(default_factory=set)
    refs: set[str] = field(default_factory=set)

    def merge(self, o: "Ev") -> None:
        for k, v in vars(o).items():
            cur = getattr(self, k)
            if isinstance(cur, set):
                cur |= v
            else:
                cur.extend(v)


class World:
    """Registry vocabularies used to read places, names and conditions."""

    def __init__(self, registry: list[dict], facts: list[dict], hospitals: set[str]) -> None:
        self.reg = registry
        self.districts = {r["district"] for r in registry}
        self.tehsils = {r["tehsil"] for r in registry}
        self.villages = {r["village"] for r in registry}
        self.place_keys = {kind: {place_key(p): p for p in vals if place_key(p)}
                           for kind, vals in (("d", self.districts), ("t", self.tehsils), ("v", self.villages))}
        self.name_tokens = {t.casefold() for r in registry for t in re.findall(r"[A-Za-z]{3,}", r["name"] + " " + r["relative_name"])}
        self.conditions = {c for c in (f.get("condition_hint") for f in facts) if c}
        self.hospitals = hospitals


def leaves(x: Any, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, k)
    elif isinstance(x, list):
        for v in x:
            yield from leaves(v, key)
    else:
        yield key, x


def extract(pairs: list[tuple[str, Any]], text: str, w: World) -> Ev:
    """Generic, format-aware evidence extraction from (field, value) pairs and free text."""
    e = Ev()
    t = text
    low = t.casefold()
    e.psns |= set(PSN.findall(t))
    for k, v in pairs:
        if v is None:
            continue
        s = str(v)
        kl = (k or "").casefold()
        if REF_KEYS.search(kl) and s.strip():
            e.refs.add(s.strip().upper())
        if re.search(r"gender|sex|ling", kl):
            g = s.strip().casefold()
            if g in ("m", "male", "पुरुष"):
                e.genders.add("M")
            elif g in ("f", "female", "महिला"):
                e.genders.add("F")
        if re.search(r"(?<![a-z])age|umar|aayu", kl) and not re.search(r"stage|page", kl):
            m = re.match(r"\s*(\d{1,3})(?:\s*-\s*(\d{1,3})|\+)?", s)
            if m:
                lo = int(m.group(1))
                hi = int(m.group(2)) if m.group(2) else (120 if "+" in s[:8] else lo)
                e.ages.append((lo, hi))
        if re.search(r"dob|birth|janm", kl):
            for h in find_dates(s):
                e.byears.add(h.value.year)
    for rx in AGE_FORMS:
        for m in rx.finditer(t):
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else lo
            if 0 < lo <= 120:
                e.ages.append((lo, hi))
    for m in BAND_PLUS.finditer(t):
        e.ages.append((int(m.group(1)), 120))
    for m in re.finditer(r"(?i)\bDOB\s*[:\-]\s*(\S+)", t):
        for h in find_dates(m.group(1)):
            e.byears.add(h.value.year)
    if re.search(r"(?<![A-Za-z])(?:\d{1,3}\s*(?:Yrs?|Y)?\s*/\s*M\b|male\b|पुरुष)", t) or re.search(r"\bS/o\b", t, re.I):
        e.genders.add("M")
    if re.search(r"(?<![A-Za-z])(?:\d{1,3}\s*(?:Yrs?|Y)?\s*/\s*F\b|female\b|महिला)", t) or re.search(r"\b[WD]/o\b", t, re.I):
        e.genders.add("F")
    for m in re.finditer(r"(?<!\d)([6-9]\d{9})(?!\d)", re.sub(r"(?<=\d)[\s-](?=\d)", "", t)):
        e.phones.add(m.group(1))
    for m in re.finditer(r"(?i)(?<![0-9A-Za-z])([6-9]\d)[x*]{4,6}(\d{2,4})(?![0-9A-Za-z])", t):
        e.masked.add((m.group(1), m.group(2)))
    e.emails |= {x.casefold() for x in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", t)}
    for m in re.finditer(r"(?i)(?:x{4}|\*{4})[\s-]?(?:x{4}|\*{4})[\s-]?(\d{4})", t):
        e.last4.add(m.group(1))
    for m in re.finditer(r"(?<!\d)(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)", t):
        e.last4.add(m.group(3))
    for m in re.finditer(r"(?<!\d)([1-8]\d{5})(?!\d)", t):
        e.pins.add(m.group(1))
    for m in re.finditer(r"(?<!\d)([1-8]\d{2})\*{3}", t):
        e.pin3.add(m.group(1))
    for m in re.finditer(r"(?i)(?:H\.?\s?No\.?|House\s*No\.?|मकान\s*नं\.?)\s*(\d{1,4})", t):
        e.houses.add(m.group(1))
    words = re.findall(r"[A-Za-z]+|[ऀ-ॿ]+", t)
    for n in range(1, 4):
        for i in range(len(words) - n + 1):
            k = place_key(" ".join(words[i:i + n]))
            if not k:
                continue
            for kind, attr in (("d", e.districts), ("t", e.tehsils), ("v", e.villages)):
                if k in w.place_keys[kind]:
                    attr.add(w.place_keys[kind][k])
    nodoc = re.sub(r"(?i)\bDr\.?\s+[A-Za-z]+(?:\s+[A-Za-z]+){0,2}", " ", t)
    e.tokens |= {x.casefold() for x in re.findall(r"[A-Za-z]{3,}", nodoc)} & w.name_tokens
    for m in re.finditer(r"[ऀ-ॿ]+(?:\s+[ऀ-ॿ]+)?", nodoc):
        k = name_key(m.group(0))
        if k:
            e.name_keys.add(k)
    for m in re.finditer(r"(?i)\b(?:S|D|W|C)/O\.?\s*[:\-]?\s*([A-Za-z]+(?:\s+[A-Za-z]+){0,2})", nodoc):
        k = name_key(m.group(1))
        if k:
            e.rel_keys.add(k)
    for h in find_dates(t):
        e.dates.add(h.value)
    ds = sorted({h.value for h in find_dates(t)})
    for i in range(len(ds)):
        for j in range(i + 1, len(ds)):
            e.intervals.add((ds[j] - ds[i]).days)
    for c in w.conditions:
        if c.casefold() in low:
            e.conditions.add(c)
    for h in w.hospitals:
        if h.casefold() in low:
            e.hospitals.add(h)
    return e


# --------------------------------------------------------------------------- registry attack

def link(e: Ev, w: World, ref_year: int) -> dict[str, float]:
    """Probability over registry people for one record / profile (A2/A3 rules)."""
    cands = w.reg

    def filt(pred) -> None:  # type: ignore[no-untyped-def]
        nonlocal cands
        nxt = [r for r in cands if pred(r)]
        if nxt:
            cands = nxt

    if e.phones:
        filt(lambda r: r["phone"].replace(" ", "")[-10:] in e.phones)
    if e.emails:
        filt(lambda r: r["email"].casefold() in e.emails)
    if e.last4:
        filt(lambda r: r["aadhaar_last4"] in e.last4)
    if e.masked:
        filt(lambda r: any(r["phone"][-10:].startswith(a) and r["phone"].endswith(b) for a, b in e.masked))
    if e.districts:
        filt(lambda r: r["district"] in e.districts)
    if len(e.genders) == 1:
        g = next(iter(e.genders))
        filt(lambda r: r["gender"].upper()[:1] == g)
    if e.ages:
        lo = max(a for a, _ in e.ages)
        hi = min(b for _, b in e.ages)
        if lo <= hi:
            filt(lambda r: lo - 1 <= int(r["age"]) <= hi + 2)
    if e.byears:
        filt(lambda r: any(abs((ref_year - int(r["age"])) - y) <= 1 for y in e.byears))
    if e.tehsils:
        filt(lambda r: r["tehsil"] in e.tehsils)
    if e.villages:
        filt(lambda r: r["village"] in e.villages)
    if e.pins:
        filt(lambda r: r["pin"] in e.pins)
    if e.pin3:
        filt(lambda r: r["pin"][:3] in e.pin3)
    weights: dict[str, float] = {}
    for r in cands:
        toks = [t.casefold() for t in re.findall(r"[A-Za-z]{3,}", r["name"])]
        wgt = 1.0
        if toks and (all(t in e.tokens for t in toks) or name_key(r["name"]) in e.name_keys):
            wgt *= 60
        else:
            if toks and toks[0] in e.tokens:
                wgt *= 8
            if len(toks) > 1 and toks[-1] in e.tokens:
                wgt *= 3
        if name_key(r["relative_name"]) in e.rel_keys:
            wgt *= 8
        if re.sub(r"\D", "", r["house_no"]) in e.houses:
            wgt *= 2
        weights[r["rid"]] = wgt
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}


# --------------------------------------------------------------------------- dataset loading

@dataclass
class Rec:
    pid: str | None
    ev: Ev
    file: str


def load_records(root: Path, files: dict[str, dict], resolve: dict[str, str], w: World) -> list[Rec]:
    """Records of a dataset (raw: root=input; release: root=output with sanitized paths)."""
    recs: list[Rec] = []
    for rel, f in files.items():
        out = resolve.get(f["sha256"])
        if not out:
            continue
        p = root / out
        if not p.is_file():
            continue
        raw = p.read_bytes()
        try:
            text = (raw[2:] if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw).decode(
                "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        text = text.lstrip("﻿")
        fmt = f.get("format")
        data: Any = None
        if fmt in ("json", "fhir") or text.lstrip()[:1] in "{[":
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        rows: list[list[str]] = []
        if fmt in ("csv", "tsv") and data is None:
            rows = list(csv.reader(text.splitlines(), delimiter="\t" if fmt == "tsv" else ","))
        for loc, u in f["units"].items():
            if loc.startswith("@"):
                continue
            pairs: list[tuple[str, Any]] = []
            body = text
            if loc.startswith("row:") and rows:
                i = int(loc[4:]) + 1
                if i < len(rows):
                    pairs = list(zip(rows[0], rows[i]))
                    body = " | ".join(f"{h}: {c}" for h, c in pairs)
            elif loc.startswith("/") and data is not None:
                node = data
                try:
                    for tok in loc.split("/")[1:]:
                        tok = tok.replace("~1", "/").replace("~0", "~")
                        node = node[int(tok)] if isinstance(node, list) else node[tok]
                except (KeyError, IndexError, ValueError, TypeError):
                    continue
                pairs = list(leaves(node))
                body = " | ".join(f"{k}: {v}" for k, v in pairs)
            elif data is not None:
                pairs = list(leaves(data))
            recs.append(Rec(u.get("patient"), extract(pairs, body, w), rel))
    return recs


def profiles(recs: list[Rec]) -> list[list[int]]:
    """Group records sharing an in-data pseudonym or a reference value (union-find)."""
    parent = list(range(len(recs)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[str, int] = {}
    for i, r in enumerate(recs):
        for key in sorted(r.ev.psns | {"ref:" + x for x in r.ev.refs}):
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(recs)):
        groups[find(i)].append(i)
    return list(groups.values())


# --------------------------------------------------------------------------- the attacks

def attack(recs: list[Rec], w: World, facts: list[dict], rid_of: dict[str, str], ref_year: int) -> dict[str, Any]:
    patient_recs = [r for r in recs if r.pid]
    rec_prob = [link(r.ev, w, ref_year).get(rid_of.get(r.pid, ""), 0.0) for r in patient_recs]
    a23 = sum(rec_prob) / max(len(rec_prob), 1)
    groups = profiles(recs)
    prof_ev: list[Ev] = []
    prof_pids: list[Counter[str]] = []
    for g in groups:
        e = Ev()
        for i in g:
            e.merge(recs[i].ev)
        prof_ev.append(e)
        prof_pids.append(Counter(recs[i].pid for i in g if recs[i].pid))
    identified: set[str] = set()
    prof_best: list[tuple[str, float]] = []
    for e, pids in zip(prof_ev, prof_pids):
        probs = link(e, w, ref_year)
        best = max(probs.items(), key=lambda kv: kv[1]) if probs else ("", 0.0)
        prof_best.append(best)
        for pid in pids:
            if probs.get(rid_of.get(pid, ""), 0.0) >= 0.5:
                identified.add(pid)
    for r, p in zip(patient_recs, rec_prob):
        if p >= 0.5:
            identified.add(r.pid)  # type: ignore[arg-type]
    n_patients = len({r.pid for r in patient_recs})
    a4 = len(identified) / max(n_patients, 1)

    # A5: targeted attack with global shift recovery
    pid_of_rid = {v: k for k, v in rid_of.items()}
    offsets: Counter[int] = Counter()
    anchors: dict[int, set[str]] = defaultdict(set)
    for (rid, conf), e in zip(prof_best, prof_ev):
        if conf >= 0.9:
            for f in facts:
                if f["rid"] == rid:
                    for d in f["visit_dates"]:
                        kd = dt.date.fromisoformat(d)
                        for pd in e.dates:
                            off = (kd - pd).days
                            if abs(off) <= 400:
                                offsets[off] += 1
                                anchors[off].add(rid)
    shift = 0
    agreed = [o for o, people in anchors.items() if len(people) >= 2]
    if agreed:
        shift = max(agreed, key=lambda o: (len(anchors[o]), offsets[o]))
    cond_count: Counter[str] = Counter(c for e in prof_ev for c in e.conditions)
    successes, false_claims, targets = [], 0, 0
    reg_by_rid = {r["rid"]: r for r in w.reg}
    for f in facts:
        person = reg_by_rid.get(f["rid"])
        if person is None:
            continue
        targets += 1
        known = {dt.date.fromisoformat(d) for d in f["visit_dates"]}
        scores: dict[int, float] = {}
        for j, e in enumerate(prof_ev):
            dates = {d + dt.timedelta(days=shift) for d in e.dates}
            s = 0.0
            if known & dates:
                s += 1
            c = f.get("condition_hint")
            if c and c in e.conditions:
                s += 8 if cond_count[c] <= 3 else 1
            if not s:
                continue
            if f.get("hospital") and f["hospital"] in e.hospitals:
                s *= 2
            if len(e.genders) == 1 and next(iter(e.genders)) != person["gender"].upper()[:1]:
                continue
            if e.ages:
                lo, hi = max(a for a, _ in e.ages), min(b for _, b in e.ages)
                if lo <= hi and not (lo - 1 <= int(person["age"]) <= hi + 2):
                    continue
            if e.districts and person["district"] not in e.districts:
                continue
            scores[j] = s
        total = sum(scores.values())
        pid = pid_of_rid.get(f["rid"])
        if pid is None:
            false_claims += 1 if total else 0
            continue
        hit = sum(v for j, v in scores.items() if prof_pids[j].get(pid))
        successes.append(hit / total if total else 0.0)
    a5 = sum(successes) / max(len(successes), 1)
    return {"A23": a23, "A4": a4, "A5": a5, "global_shift_recovered": bool(agreed),
            "identified_patients": len(identified), "patients": n_patients, "profiles": len(groups),
            "targets": targets, "decoy_false_claims": false_claims}


def direct_exposure(root: Path, files: dict[str, dict], resolve: dict[str, str]) -> float:
    """A1: share of patients with a surviving critical identifier or full name anywhere."""
    corpus = []
    for p in root.rglob("*"):
        if p.is_file():
            corpus.append(normalise(p.relative_to(root).as_posix()))
            corpus.append(read_norm(p))
    blob = "\n".join(corpus)
    exposed, patients = set(), set()
    for f in files.values():
        for u in f["units"].values():
            for e in u["entities"]:
                pid = u.get("patient")
                if not pid or e.get("role") != "patient":
                    continue
                patients.add(pid)
                if not e.get("critical"):
                    continue
                ks = [k for k in keys_for(e) if k.kind != "translit"]
                if ks and all(k.count(blob) for k in ks):
                    exposed.add(pid)
    return len(exposed) / max(len(patients), 1)


def inversion(release: Path, truth: dict) -> float:
    """A6: share of pseudonyms that equal or prefix a transform of their own patient's originals."""
    recs = [json.loads(line) for line in (release / "records.jsonl").read_text().splitlines() if line.strip()]
    psns = {r["patient"] for r in recs if r.get("patient")}
    originals = set()
    for f in truth["files"].values():
        for u in f["units"].values():
            for e in u["entities"]:
                if e.get("critical"):
                    originals.add(e["surface"])
    forms = set()
    for o in originals:
        for v in (o, o.lower(), o.upper(), re.sub(r"\D", "", o), o[::-1]):
            if not v:
                continue
            b = v.encode()
            forms |= {v.upper(), base64.b64encode(b).decode().upper()}
            for h in (hashlib.md5, hashlib.sha1, hashlib.sha256, hashlib.sha512):
                forms.add(h(b).hexdigest().upper())
    inverted = 0
    for p in psns:
        code = p.split("-", 1)[-1].upper()
        if any(f.startswith(code) or code in f for f in forms if len(f) >= 6):
            inverted += 1
    return inverted / max(len(psns), 1)


def cross_release(a: Path, b: Path) -> float:
    """A7: share of pseudonyms that survive a secret change (by record locator)."""
    def load(p: Path) -> dict[tuple[str, str], str]:
        out = {}
        for line in (p / "records.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("patient"):
                    out[(r["file"], r["loc"])] = r["patient"]
        return out
    pa, pb = load(a), load(b)
    common = [k for k in pa if k in pb]
    return sum(pa[k] == pb[k] for k in common) / max(len(common), 1)


def run(release: Path, rotated: Path | None, inp: Path, truth_path: Path, attacker_dir: Path) -> dict[str, Any]:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    registry = list(csv.DictReader(open(attacker_dir / "registry.csv", encoding="utf-8")))
    facts = [json.loads(line) for line in open(attacker_dir / "known_facts.jsonl", encoding="utf-8") if line.strip()]
    hospitals = {f["hospital"] for f in facts if f.get("hospital")}
    w = World(registry, facts, hospitals)
    rid_of = {pid: p["rid"] for pid, p in truth["patients"].items()}
    ref_year = int(str(truth.get("ref_date", "2026"))[:4])
    files = truth["files"]
    raw_map = {f["sha256"]: rel for rel, f in files.items()}
    report = json.loads((release / "report.json").read_text(encoding="utf-8"))
    rel_map = {e["input_sha256"]: e["output"] for e in report["files"] if e.get("output")}
    raw = attack(load_records(inp, files, raw_map, w), w, facts, rid_of, ref_year)
    out = attack(load_records(release, files, rel_map, w), w, facts, rid_of, ref_year)
    a1_raw = direct_exposure(inp, files, raw_map)
    a1 = direct_exposure(release, files, rel_map)
    risks = {
        "A1": a1 / max(a1_raw, 1e-9),
        "A23": out["A23"] / max(raw["A23"], 1e-9),
        "A4": out["A4"] / max(raw["A4"], 1e-9),
        "A5": out["A5"] / max(raw["A5"], 1e-9),
        "A6": inversion(release, truth),
    }
    if rotated is not None:
        risks["A7"] = cross_release(release, rotated)
    wsum = sum(WEIGHTS[k] for k in risks)
    risk = sum(WEIGHTS[k] * min(v, 1.0) for k, v in risks.items()) / wsum
    return {"risk": round(risk, 4), "resistance": round(1 - risk, 4),
            "risks": {k: round(min(v, 1.0), 4) for k, v in risks.items()},
            "raw": {"A1": round(a1_raw, 4), **{k: round(v, 4) if isinstance(v, float) else v for k, v in raw.items()}},
            "release": {"A1": round(a1, 4), **{k: round(v, 4) if isinstance(v, float) else v for k, v in out.items()}}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Anamika attack arena (prints rates only)")
    ap.add_argument("--release", required=True)
    ap.add_argument("--rotated", default=None, help="a second release made with a different secret (A7)")
    ap.add_argument("--kit", default=str(DEFAULT_KIT))
    ap.add_argument("--input", default=None)
    ap.add_argument("--truth", default=None)
    ap.add_argument("--attacker", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    kit = Path(a.kit)
    res = run(Path(a.release), Path(a.rotated) if a.rotated else None,
              Path(a.input or kit / "dev" / "input"), Path(a.truth or kit / "dev" / "truth" / "truth.json"),
              Path(a.attacker or kit / "dev" / "attacker"))
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    r, raw, rel = res["risks"], res["raw"], res["release"]
    print(f"ATTACK ARENA  risk {res['risk']:.3f}  resistance {res['resistance']:.3f}  "
          f"(≈ {25 * res['resistance']:.1f}/25 if utility ≥ 0.40)")
    print(f"  A1 direct exposure      raw {raw['A1']:.2%}  release {rel['A1']:.2%}  ratio {r['A1']:.3f}")
    print(f"  A2/A3 record linkage    raw {raw['A23']:.2%}  release {rel['A23']:.2%}  ratio {r['A23']:.3f}")
    print(f"  A4 profile re-id        raw {raw['A4']:.2%} ({raw['identified_patients']}/{raw['patients']})  "
          f"release {rel['A4']:.2%} ({rel['identified_patients']}/{rel['patients']})  ratio {r['A4']:.3f}")
    print(f"  A5 targeted             raw {raw['A5']:.2%}  release {rel['A5']:.2%}  ratio {r['A5']:.3f}  "
          f"(global shift recovered: raw {raw['global_shift_recovered']}, release {rel['global_shift_recovered']}; "
          f"decoy false claims {rel['decoy_false_claims']})")
    print(f"  A6 pseudonym inversion  {r['A6']:.2%}")
    if "A7" in r:
        print(f"  A7 cross-release        {r['A7']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
