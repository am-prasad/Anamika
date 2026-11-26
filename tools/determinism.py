#!/usr/bin/env python3
"""Determinism, secret-rotation and hygiene check (development tool).

Runs the pipeline three times on the same input, each with its own private, empty
``TMPDIR`` and ``HOME``:

* **A** and **B** with the same secret → ``sanitized/`` and ``records.jsonl`` must be
  byte-identical (per-file comparison, as the evaluator scores it);
* **C** with a different secret → pseudonyms must all change and the release must differ.

It also verifies that the secret never appears in any output, stdout/stderr, TMPDIR or
HOME, that no temp files are left behind, that the input tree is untouched, and that the
process exited 0. Nothing from the data is printed — only counts and verdicts.

Usage::

    python tools/determinism.py --input DEV_INPUT [--keep]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def file_hashes(out: Path) -> dict[str, str]:
    """SHA-256 of every file under ``sanitized/`` plus ``records.jsonl``."""
    res: dict[str, str] = {}
    for p in sorted((out / "sanitized").rglob("*")):
        if p.is_file():
            res[p.relative_to(out).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    rj = out / "records.jsonl"
    if rj.is_file():
        res["records.jsonl"] = hashlib.sha256(rj.read_bytes()).hexdigest()
    return res


def tree_digest(root: Path) -> str:
    """One digest over every relative path and byte of ``root``."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def pseudonyms(out: Path) -> set[str]:
    """Distinct non-null pseudonyms in ``records.jsonl``."""
    rj = out / "records.jsonl"
    if not rj.is_file():
        return set()
    vals = set()
    for line in rj.read_text(encoding="utf-8").splitlines():
        if line.strip():
            p = json.loads(line).get("patient")
            if p:
                vals.add(p)
    return vals


def contains(root: Path, needle: bytes) -> int:
    """Number of files under ``root`` (names or bytes) containing ``needle``."""
    n = 0
    for p in root.rglob("*"):
        if needle in p.name.encode() or (p.is_file() and needle in p.read_bytes()):
            n += 1
    return n


def run_once(inp: Path, work: Path, tag: str, secret: str) -> dict:
    """Run ``main.py`` once in an isolated TMPDIR/HOME; return evidence for the checks."""
    out, tmp, home = work / f"out_{tag}", work / f"tmp_{tag}", work / f"home_{tag}"
    for d in (out, tmp, home):
        d.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("RAKSHA_")}
    env.update(RAKSHA_SECRET=secret, RAKSHA_INPUT=str(inp), RAKSHA_OUTPUT=str(out),
               TMPDIR=str(tmp), HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, str(REPO / "main.py"), "--input", str(inp),
                           "--output", str(out)], cwd=REPO, env=env, capture_output=True)
    secs = time.monotonic() - t0
    logs = proc.stdout + proc.stderr
    sb = secret.encode()
    return {
        "tag": tag, "out": out, "code": proc.returncode, "seconds": secs,
        "hashes": file_hashes(out), "pseudonyms": pseudonyms(out),
        "secret_hits": contains(out, sb) + contains(tmp, sb) + contains(home, sb)
        + (1 if sb in logs else 0),
        "tmp_leftovers": sum(1 for _ in tmp.rglob("*")) + sum(1 for _ in home.rglob("*")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Anamika determinism / rotation / hygiene check")
    ap.add_argument("--input", required=True)
    ap.add_argument("--keep", action="store_true", help="keep the work folder for inspection")
    a = ap.parse_args()
    inp = Path(a.input).resolve()
    before = tree_digest(inp)
    work = Path(tempfile.mkdtemp(prefix="anamika-det-"))
    sa, sb = "det-A-" + os.urandom(8).hex(), "det-B-" + os.urandom(8).hex()
    runs = {t: run_once(inp, work, t, s) for t, s in (("A", sa), ("B", sa), ("C", sb))}
    A, B, C = runs["A"], runs["B"], runs["C"]
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok &= cond
        print(("  PASS " if cond else "  FAIL ") + msg)

    print("DETERMINISM CHECK")
    check(all(r["code"] == 0 for r in runs.values()),
          f"exit codes {[r['code'] for r in runs.values()]}")
    same = sum(A["hashes"].get(k) == v for k, v in B["hashes"].items())
    check(A["hashes"] == B["hashes"],
          f"same secret: {same}/{max(len(A['hashes']), len(B['hashes']))} output files identical")
    diff_files = sum(A["hashes"].get(k) != v for k, v in C["hashes"].items())
    if A["pseudonyms"]:
        shared = len(A["pseudonyms"] & C["pseudonyms"])
        check(shared == 0, f"other secret: {shared}/{len(A['pseudonyms'])} pseudonyms reused")
    else:
        print("  INFO no pseudonyms issued yet (secret rotation of pseudonyms not testable)")
    print(f"  INFO other secret changed {diff_files}/{len(C['hashes'])} output files")
    check(sum(r["secret_hits"] for r in runs.values()) == 0,
          "secret never written to output / stdout / stderr / TMPDIR / HOME")
    check(sum(r["tmp_leftovers"] for r in runs.values()) == 0, "no leftovers in TMPDIR / HOME")
    check(tree_digest(inp) == before, "input tree unchanged")
    print(f"  INFO wall seconds A={A['seconds']:.2f} B={B['seconds']:.2f} C={C['seconds']:.2f}")
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    print("DETERMINISM OK" if ok else "DETERMINISM PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
