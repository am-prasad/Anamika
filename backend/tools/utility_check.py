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
import json
import re
import sys
from collections import Counter
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
    return {
        "probes": {kind: [kept[kind], probes[kind]] for kind in sorted(probes)},
        "probe_total": [sum(kept.values()), sum(probes.values())],
        "token_retention": round(ret_kept / max(ret_in, 1), 4),
        "clean_token_retention": round(clean_kept / max(clean_in, 1), 4),
        "worst_files": [(round(r, 3), re.sub(r"\d", "#", rel.split("/")[0])) for r, rel in sorted(per_file)[:worst]],
    }


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
    lost = {kind: f"{a}/{b}" for kind, (a, b) in res["probes"].items() if a < b}
    print("  probe kinds with losses: " + (", ".join(f"{k} {v}" for k, v in lost.items()) or "none"))
    print("  lowest-retention files (folder): " + ", ".join(f"{f}:{r}" for r, f in res["worst_files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
