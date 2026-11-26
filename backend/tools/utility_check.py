#!/usr/bin/env python3
"""Utility self-check: what clinical value survives (development tool, never prints values).

Mirrors two parts of the official utility / precision scoring:

* **preserve-probes by kind** — share of the answer key's ``preserve`` texts (medication,
  dose, frequency, vitals, labs, diagnoses, doctor lines, wards, eponyms, complaints…) still
  present in the exported record's file;
* **token retention** — multiset share of non-PII input tokens still present in the output
  (dates, ages, numbers and PII tokens excluded), overall and on clean documents. This is
  the over-redaction detector.

Usage::

    python tools/utility_check.py --output OUT [--input IN --truth TRUTH] [--worst 8]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.leak_scan import DEFAULT_KIT, normalise  # noqa: E402

_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")


def read_norm(p: Path) -> str:
    """Decoded, normalised text with ``\\uXXXX`` escapes resolved *in place* (so a JSON file
    that escapes Devanagari is compared like-for-like with a UTF-8 output)."""
    raw = p.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    return normalise(_UESC.sub(lambda m: chr(int(m.group(1), 16)), text))

_TOKEN = re.compile(r"[^\W\d_]{2,}|[ऀ-ॣ॰-ॿ]{2,}")


def tokens(text: str) -> Counter[str]:
    """Word tokens (no digits) of normalised text."""
    return Counter(_TOKEN.findall(text))


def check(out: Path, inp: Path, truth_path: Path, worst: int) -> dict:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    dec = {e["input_sha256"]: e.get("output") for e in report["files"]}
    probes: Counter[str] = Counter()
    kept: Counter[str] = Counter()
    ret_in = ret_kept = clean_in = clean_kept = 0
    per_file: list[tuple[float, str]] = []
    for rel, f in truth["files"].items():
        o = dec.get(f["sha256"])
        if not o:
            continue
        src, dst = read_norm(inp / rel), read_norm(out / o)
        for u in f["units"].values():
            for p in u.get("preserve") or []:
                probes[p["kind"]] += 1
                kept[p["kind"]] += normalise(p["text"]) in dst
        pii = set()
        for u in f["units"].values():
            for e in u["entities"]:
                pii.update(_TOKEN.findall(normalise(e["surface"])))
            for x in u.get("exclude") or []:
                pii.update(_TOKEN.findall(normalise(str(x))))
        tin = Counter({t: c for t, c in tokens(src).items() if t not in pii})
        tout = tokens(dst)
        k = sum(min(c, tout[t]) for t, c in tin.items())
        n = sum(tin.values())
        ret_in += n
        ret_kept += k
        if f.get("clean"):
            clean_in += n
            clean_kept += k
        if n:
            per_file.append((k / n, rel))
    los, age_ok, age_n = _temporal_and_ages(truth, dec, out, inp)
    return {
        "los": los,
        "age_truth": [age_ok, age_n],
        "probes": {kind: [kept[kind], probes[kind]] for kind in sorted(probes)},
        "probe_total": [sum(kept.values()), sum(probes.values())],
        "token_retention": round(ret_kept / max(ret_in, 1), 4),
        "clean_token_retention": round(clean_kept / max(clean_in, 1), 4),
        "worst_files": [(round(r, 3), re.sub(r"\d", "#", rel.split("/")[0])) for r, rel in sorted(per_file)[:worst]],
    }


def _record_text(path: Path, loc: str) -> str:
    """Text of one record: a CSV row, a JSON pointer subtree, or the whole document."""
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", "replace")
    else:
        text = raw.decode("utf-8", "replace").lstrip("\ufeff")
    if loc.startswith("row:"):
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t" if path.suffix == ".tsv" else ","))
        i = int(loc[4:]) + 1
        return " | ".join(rows[i]) if i < len(rows) else ""
    if loc.startswith("/"):
        try:
            node = json.loads(text)
            for tok in loc.split("/")[1:]:
                tok = tok.replace("~1", "/").replace("~0", "~")
                node = node[int(tok)] if isinstance(node, list) else node[tok]
            return json.dumps(node, ensure_ascii=False)
        except (ValueError, KeyError, IndexError, TypeError):
            return ""
    return text


def _band_holds(value: str, age: int) -> bool:
    m = re.match(r"\s*(-?\d{1,3})\s*(?:-\s*(\d{1,3})|(\+))?", value or "")
    if not m:
        return False
    lo = int(m.group(1))
    hi = 200 if m.group(3) else int(m.group(2) or lo)
    return lo <= age <= hi


def _temporal_and_ages(truth: dict, dec: dict, out: Path, inp: Path) -> tuple[list[dict], int, int]:
    """Length of stay before vs after (output dates matched by position, not by value) and
    the share of released age values whose band contains the true age."""
    from anamika.privacy.dates import find_dates

    los: list[dict] = []
    age_ok = age_n = 0
    for rel, f in truth["files"].items():
        o = dec.get(f["sha256"])
        if not o:
            continue
        for loc, u in f["units"].items():
            ds = {d.get("event"): d["true"] for d in u.get("dates") or []}
            if "admission" in ds and "discharge" in ds:
                src = [h.value.isoformat() for h in find_dates(_record_text(inp / rel, loc))]
                dst = [h.value for h in find_dates(_record_text(out / o, loc))]
                if len(src) == len(dst) and ds["admission"] in src and ds["discharge"] in src:
                    a, b = src.index(ds["admission"]), src.index(ds["discharge"])
                    before = (date.fromisoformat(ds["discharge"]) - date.fromisoformat(ds["admission"])).days
                    los.append({"before": before, "after": (dst[b] - dst[a]).days})
            for fld in u.get("fields") or []:
                if fld.get("kind") != "age" or not str(fld.get("path", "")).startswith("col:"):
                    continue
                col = fld["path"][4:]
                p = out / o
                try:
                    text = p.read_text(encoding="utf-8").lstrip("\ufeff")
                except (OSError, UnicodeDecodeError):
                    continue
                rows = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t" if p.suffix == ".tsv" else ","))
                if not rows or col not in rows[0] or not loc.startswith("row:"):
                    continue
                i = int(loc[4:]) + 1
                if i < len(rows):
                    age_n += 1
                    age_ok += _band_holds(rows[i][rows[0].index(col)], int(fld["true"]))
    return los, age_ok, age_n


def main() -> int:
    ap = argparse.ArgumentParser(description="Anamika utility self-check (counts only)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--input", default=None)
    ap.add_argument("--truth", default=None)
    ap.add_argument("--worst", type=int, default=8)
    a = ap.parse_args()
    kit = DEFAULT_KIT
    res = check(Path(a.output), Path(a.input or kit / "dev" / "input"),
                Path(a.truth or kit / "dev" / "truth" / "truth.json"), a.worst)
    k, n = res["probe_total"]
    print(f"UTILITY  probes kept {k}/{n}  token retention {res['token_retention']:.2%}  "
          f"clean-doc retention {res['clean_token_retention']:.2%}")
    exact = sum(1 for x in res["los"] if x["before"] == x["after"])
    print(f"  length of stay exact {exact}/{len(res['los'])}  age bands truthful {res['age_truth'][0]}/{res['age_truth'][1]}")
    lost = {kind: f"{a}/{b}" for kind, (a, b) in res["probes"].items() if a < b}
    print("  probe kinds with losses: " + (", ".join(f"{k} {v}" for k, v in lost.items()) or "none"))
    print("  lowest-retention files (folder): " + ", ".join(f"{f}:{r}" for r, f in res["worst_files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
