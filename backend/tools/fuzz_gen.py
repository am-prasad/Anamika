#!/usr/bin/env python3
"""Fuzz generator: turns the practice set into "never-seen" variants with a matching answer key.

Development tool (not part of the pipeline). Each variant applies, deterministically from a
seed:

* **new people** — every name token of the answer key (Latin and Devanagari) is replaced by
  an invented token from a syllable grammar, consistently across all files, file names and
  the answer key, so nothing the pipeline was tuned on survives;
* **new labels** — CSV headers, JSON keys and free-text labels get unseen synonyms
  (``Patient Name`` → ``Name of Patient``, ``Mobile:`` → ``Contact No.:``, ``नाम:`` → ``रोगी का नाम:``);
* **new formats** — dates of birth re-rendered (``12/04/1977`` → ``12-Apr-1977``), some tables
  re-encoded (UTF-16, cp1252), and extra unsupported or broken files (zip, xlsx, NDJSON,
  truncated JSON, binary with a PII-looking name, Devanagari file name).

The output folder mirrors the kit layout (``input/`` + ``truth/truth.json``) with SHA-256s
recomputed, so ``check_dev.py --truth`` and ``tools/leak_scan.py --input/--truth`` score it.
Nothing is printed except counts.

Usage::

    python tools/fuzz_gen.py --kit KIT --out DIR [--seed 7] [--variants 3]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import shutil
from pathlib import Path

LATIN_ON = ["b", "bh", "ch", "d", "dh", "g", "h", "j", "k", "kh", "l", "m", "n", "p", "r", "s", "sh",
            "t", "v", "y", "z"]
LATIN_NU = ["a", "aa", "e", "i", "o", "u", "ee", "ai"]
LATIN_CO = ["", "n", "r", "l", "sh", "t", "m", "v", "nd", "sh"]
DEVA_CONS = list("कखगघचजझटडतथदधनपफबभमयरलवशसह")
DEVA_VOW = ["ा", "ि", "ी", "ु", "ू", "े", "ो", ""]

HEADER_VARIANTS = {
    "patient name": "Name of Patient", "naam": "Mareez", "name": "Full Name", "mobile": "Contact#",
    "mobile no": "Phone Number", "phone": "Contact No", "village/mohalla": "Gram/Mohalla",
    "gaon": "Gram", "aadhaar no": "UID No.", "aadhar": "Aadhar Card", "abha no": "Health ID",
    "dob": "Birth Dt", "janm tithi": "Janam Taarikh", "relative name": "Guardian",
    "pita/pati ka naam": "Abhibhavak", "umar": "Aayu", "age": "Age (yrs)", "pin": "Postal Code",
    "pin code": "Pincode", "uhid": "Hospital No", "reg no": "Registration Number",
    "patient_name": "pt_name", "hospital_uhid": "hosp_reg_no", "patient_ref": "pt_id",
    "address": "Residence", "pata": "Niwas", "relation": "Rel.", "district": "Zila",
}
KEY_VARIANTS = {"patient_ref": "pt_id", "patient_name": "pname", "mobile": "contact_no",
                "phone": "mob_no", "hospital_uhid": "reg_no", "name": "full_name",
                "callback": "call_back_no", "dob": "birth_date", "village": "gram"}
LABEL_VARIANTS = [
    (r"(?m)^Patient Name:", "Name of Patient:"), (r"(?m)^Name:", "Pt Name:"),
    (r"Mobile:", "Contact No.:"), (r"(?m)^Mob:", "Ph:"), (r"Attendant:", "Accompanied by:"),
    (r"(?<![A-Za-z])S/o ", "Son of "), (r"(?<![A-Za-z])W/o ", "Wife of "),
    (r"नाम:", "रोगी का नाम:"), (r"(?m)^Address:", "Residential Address:"),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def latin_name(rng: random.Random, used: set[str]) -> str:
    """An invented, pronounceable Latin name token not used before."""
    while True:
        n = "".join(rng.choice(LATIN_ON) + rng.choice(LATIN_NU) for _ in range(rng.choice((2, 2, 3))))
        n = (n + rng.choice(LATIN_CO)).capitalize()
        if 4 <= len(n) <= 11 and n.casefold() not in used:
            used.add(n.casefold())
            return n


def deva_name(rng: random.Random, used: set[str]) -> str:
    """An invented Devanagari name token."""
    while True:
        n = "".join(rng.choice(DEVA_CONS) + rng.choice(DEVA_VOW) for _ in range(rng.choice((2, 3))))
        if n not in used:
            used.add(n)
            return n


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace"), "cp1252"


def encode(text: str, enc: str) -> bytes:
    if enc == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    if enc == "utf-16":
        return text.encode("utf-16")
    if enc == "cp1252":
        return text.encode("cp1252", "replace")
    return text.encode("utf-8")


def build_name_map(truth: dict, rng: random.Random) -> dict[str, str]:
    """Every identifying name token of the answer key → an invented token."""
    used: set[str] = set()
    mapping: dict[str, str] = {}
    toks: set[str] = set()
    for f in truth["files"].values():
        for u in f["units"].values():
            for e in u["entities"]:
                if e["match"] == "name":
                    toks.update(re.findall(r"[A-Za-z]{3,}|[ऀ-ॿ]{2,}", e["surface"]))
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from anamika.detect.lexicon import GENERIC_NAME_TOKENS, POST_HONORIFICS, POST_HONORIFICS_DEVA
    honorifics = set(re.findall(r"[a-z]+|[\u0900-\u097F]+", POST_HONORIFICS + POST_HONORIFICS_DEVA))
    generic = set(GENERIC_NAME_TOKENS) | honorifics | {"singh", "lal", "सिंह", "लाल"}
    for t in sorted(toks):
        if t.casefold() in generic or t in generic:
            continue
        if re.match(r"[A-Za-z]", t):
            if t.casefold() not in mapping:
                mapping[t.casefold()] = latin_name(rng, used)
        else:
            mapping[t] = deva_name(rng, used)
    return mapping


def apply_names(text: str, mapping: dict[str, str], rx_lat: re.Pattern[str], rx_deva: re.Pattern[str] | None) -> str:
    def lat(m: re.Match[str]) -> str:
        src, new = m.group(0), mapping[m.group(0).casefold()]
        if src.isupper():
            return new.upper()
        if src.islower():
            return new.lower()
        return new

    text = rx_lat.sub(lat, text)
    if rx_deva is not None:
        text = rx_deva.sub(lambda m: mapping[m.group(0)], text)
    return text


def reformat_dob(iso: str) -> tuple[list[str], str]:
    d = dt.date.fromisoformat(iso)
    olds = [f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day:02d}-{d.month:02d}-{d.year}",
            f"{d.month:02d}/{d.day:02d}/{d.year}"]
    return olds, f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def make_variant(kit: Path, out: Path, seed: int) -> dict[str, int]:
    rng = random.Random(seed)
    truth = json.loads((kit / "dev" / "truth" / "truth.json").read_text(encoding="utf-8"))
    src = kit / "dev" / "input"
    mapping = build_name_map(truth, rng)
    lat_keys = sorted((k for k in mapping if re.match(r"[a-z]", k)), key=len, reverse=True)
    deva_keys = sorted((k for k in mapping if not re.match(r"[a-z]", k)), key=len, reverse=True)
    rx_lat = re.compile(r"(?<![A-Za-z])(?:" + "|".join(map(re.escape, lat_keys)) + r")(?![A-Za-z])", re.I)
    rx_deva = re.compile(r"(?<![ऀ-ॿ])(?:" + "|".join(map(re.escape, deva_keys)) + r")(?![ऀ-ॿ])") \
        if deva_keys else None
    dob_map: dict[str, str] = {}
    for f in truth["files"].values():
        for u in f["units"].values():
            for e in u["entities"]:
                if e["type"] == "DOB" and e.get("key"):
                    olds, new = reformat_dob(e["key"])
                    for o in olds:
                        dob_map[o] = new
    if out.exists():
        shutil.rmtree(out)
    (out / "input").mkdir(parents=True)
    (out / "truth").mkdir()
    stats = {"files": 0, "renamed_headers": 0, "reencoded": 0, "names": len(mapping), "extras": 0}
    new_files: dict[str, dict] = {}
    for rel, f in truth["files"].items():
        raw = (src / rel).read_bytes()
        new_rel = apply_names(rel, mapping, rx_lat, rx_deva)
        target = out / "input" / new_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if f["format"] in ("pdf", "binary", "xml") or not raw.strip() or f.get("expect") == "either":
            target.write_bytes(raw)
        else:
            text, enc = decode(raw)
            text = apply_names(text, mapping, rx_lat, rx_deva)
            for o, n in dob_map.items():
                text = text.replace(o, n)
            if f["format"] in ("csv", "tsv"):
                lines = text.split("\n", 1)
                delim = "\t" if f["format"] == "tsv" else ","
                hdr = lines[0].split(delim)
                hdr2 = [HEADER_VARIANTS.get(h.strip().lstrip("﻿").casefold(), h) for h in hdr]
                stats["renamed_headers"] += sum(a != b for a, b in zip(hdr, hdr2))
                text = delim.join(hdr2) + ("\n" + lines[1] if len(lines) > 1 else "")
                if enc == "utf-8" and rng.random() < 0.3:
                    enc = "utf-16" if re.search(r"[ऀ-ॿ]", text) or rng.random() < 0.5 else "cp1252"
                    stats["reencoded"] += 1
            elif f["format"] in ("json", "fhir") and f["format"] != "fhir":
                for k, v in KEY_VARIANTS.items():
                    text = re.sub(rf'"{re.escape(k)}"(\s*:)', f'"{v}"\\1', text)
            else:
                for pat, rep in LABEL_VARIANTS:
                    text = re.sub(pat, rep, text)
            target.write_bytes(encode(text, enc))
        nf = json.loads(apply_names(json.dumps(f, ensure_ascii=False), mapping, rx_lat, rx_deva))
        for u in nf["units"].values():
            for e in u["entities"]:
                if e["type"] == "DOB":
                    for o, n in dob_map.items():
                        e["surface"] = e["surface"].replace(o, n)
        nf["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        nf["path"] = new_rel
        new_files[new_rel] = nf
        stats["files"] += 1
    # extra unseen / broken files (expect=either; must be quarantined or cleaned, never copied raw)
    extras = {
        "misc/archive_export.zip": b"PK\x03\x04" + bytes(rng.randrange(256) for _ in range(200)),
        "misc/register.xlsx": b"PK\x03\x04[Content_Types].xml" + bytes(64),
        "misc/visits.ndjson.json": b'{"a": 1}\n{"b": 2}\n',
        "misc/half_written.json": b'{"patients": [{"name": "' + mapping[lat_keys[0]].encode() + b'", "mob',
        f"misc/{mapping[lat_keys[1]]}_9876501234_scan.bin": bytes(range(256)) * 4,
        f"misc/{mapping[deva_keys[0]] if deva_keys else 'x'}_पर्चा.txt": "पर्चा\n".encode(),
    }
    for rel, data in extras.items():
        p = out / "input" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        units = {}
        if "_scan.bin" in rel or "पर्चा" in rel:
            units["@filename"] = {"loc": "@filename", "patient": None, "link": "none", "tags": [],
                                  "entities": [{"type": "PATIENT_NAME", "surface": rel.split("/")[1].split("_")[0],
                                                "person": None, "role": "patient", "script": "latin" if "bin" in rel else "deva",
                                                "channel": "filename", "match": "name", "critical": True}],
                                  "preserve": [], "dates": [], "fields": [], "exclude": []}
        valid_text = rel.endswith(".txt")
        new_files[rel] = {"path": rel, "format": "text" if valid_text else "binary", "encoding": "",
                          "delimiter": None, "expect": "sanitize" if valid_text else "either",
                          "category": "fuzz", "clean": False, "sha256": hashlib.sha256(data).hexdigest(),
                          "size": len(data), "generalizable": [], "units": units}
        stats["extras"] += 1
    for rel, data, units in novel_templates(rng):
        p = out / "input" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        new_files[rel] = {"path": rel, "format": rel.rsplit(".", 1)[1].replace("txt", "text"),
                          "encoding": "utf-8", "delimiter": "," if rel.endswith(".csv") else None,
                          "expect": "sanitize", "category": "novel", "clean": False,
                          "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                          "generalizable": [], "units": units}
        stats["extras"] += 1
    truth["files"] = new_files
    truth["canaries"] = [apply_names(c, mapping, rx_lat, rx_deva) for c in truth.get("canaries", [])]
    (out / "truth" / "truth.json").write_text(json.dumps(truth, ensure_ascii=False), encoding="utf-8")
    return stats


def _ent(etype: str, surface: str, script: str = "latin", role: str = "patient",
         match: str | None = None) -> dict:
    m = match or {"PATIENT_NAME": "name", "RELATIVE_NAME": "name", "PHONE": "digits"}.get(etype, "text")
    return {"type": etype, "surface": surface, "person": None, "role": role, "script": script,
            "channel": "content", "match": m, "critical": etype in ("PATIENT_NAME", "PHONE"),
            "key": "".join(c for c in surface if c.isdigit()) if m == "digits" else surface}


def _unit(loc: str, ents: list[dict], preserve: list[str]) -> dict:
    return {"loc": loc, "patient": None, "link": "none", "tags": ["novel"], "entities": ents,
            "preserve": [{"text": t, "kind": "clinical", "weight": 1.0, "path": None} for t in preserve],
            "dates": [], "fields": [], "exclude": []}


def novel_templates(rng: random.Random) -> list[tuple[str, bytes, dict]]:
    """Formats and labels that never appear in the practice data, with their answer key."""
    used: set[str] = set()
    out = []
    people = [(latin_name(rng, used) + " " + latin_name(rng, used),
               "9" + "".join(str(rng.randrange(10)) for _ in range(9)),
               latin_name(rng, used) + " Khurd") for _ in range(4)]
    # 1. nested EMR JSON with unseen keys
    recs, units = [], {}
    for i, (name, ph, vill) in enumerate(people[:2]):
        recs.append({"personal": {"fullName": name, "contactNumber": ph,
                                  "residence": {"houseNo": f"H-{rng.randrange(10, 400)}", "village": vill,
                                                "pincode": "2290" + str(rng.randrange(10, 99))}},
                     "clinical": {"dx": "Typhoid fever", "rx": "Tab Azithromycin 500 mg OD x 3 days"}})
        units[f"/records/{i}"] = _unit(f"/records/{i}", [_ent("PATIENT_NAME", name), _ent("PHONE", ph),
                                                         _ent("VILLAGE", vill)],
                                       ["Typhoid fever", "Tab Azithromycin 500 mg OD x 3 days"])
    out.append(("novel/emr_export.json", json.dumps({"records": recs}, indent=1).encode(), units))
    # 2. CSV with unseen headers
    rows = ["Beneficiary,Cell,Locality,Clinical Notes"]
    units = {}
    for i, (name, ph, vill) in enumerate(people[2:]):
        rows.append(f"{name},{ph[:5]} {ph[5:]},{vill},Dengue NS1 positive; Platelets 85000 /uL")
        units[f"row:{i}"] = _unit(f"row:{i}", [_ent("PATIENT_NAME", name), _ent("PHONE", ph[:5] + " " + ph[5:]),
                                               _ent("VILLAGE", vill)], ["Platelets 85000 /uL"])
    out.append(("novel/scheme_list.csv", ("\n".join(rows) + "\n").encode(), units))
    # 3. pipe-delimited OPD slip with new labels
    name, ph, vill = people[0]
    rel = latin_name(rng, used) + " " + name.split()[1]
    slip = (f"OPD SLIP | Pt: {name} | Mob- {ph} | Gram- {vill}\n"
            f"Accompanied by: {rel} (husband)\nComplaint: fever with chills x 4 days\n"
            "Rx: Tab Paracetamol 650 mg TDS x 3 days\nSeen by Dr. Kamal Nayan Bajaj\n")
    out.append(("novel/opd_slip_17.txt", slip.encode(),
                {"doc": _unit("doc", [_ent("PATIENT_NAME", name), _ent("PHONE", ph), _ent("VILLAGE", vill),
                                      _ent("RELATIVE_NAME", rel, role="relative")],
                              ["Tab Paracetamol 650 mg TDS x 3 days", "Dr. Kamal Nayan Bajaj"])}))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Anamika fuzz generator (prints counts only)")
    ap.add_argument("--kit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--variants", type=int, default=1)
    a = ap.parse_args()
    for i in range(a.variants):
        stats = make_variant(Path(a.kit), Path(a.out) / f"fuzz_{a.seed + i}", a.seed + i)
        print(f"fuzz_{a.seed + i}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
