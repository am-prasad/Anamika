"""Top-level runner: argument parsing, the guarded two-pass pipeline and exit codes.

Pass A reads, hashes, decodes and parses every input, then the :class:`Pipeline` learns
the dataset (lexicon, evidence, linkage). Pass B rewrites each parsed file and writes it
under ``sanitized/`` (renamed when the file name holds PII). Any failure in either pass
quarantines that file with a closed-vocabulary reason; no partial output is ever
written. Exit code 0 is returned only when every input file is accounted for in
``report.json``.

Exit codes: 0 complete release · 1 accounting failure or fatal error · 2 bad invocation
or missing secret.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Mapping

from . import policy as pol
from .ingest.csv_io import read_table
from .ingest.json_io import load_json, record_pointers
from .ingest.sniff import QuarantineError, decode_bytes, detect_format
from .pipeline import Item, Pipeline, rid
from .privacy.dates import infer_order
from .report import FileEntry, Record, RunReport, peak_rss_mb
from .safety import LOG, Keyring, SecretMissing, install_guards, set_stage, sha_prefix

#: formats whose legacy exports may legitimately be cp1252; free-text notes must be UTF-8
_LEGACY_OK = {"csv", "tsv"}


def walk_inputs(root: Path) -> list[Path]:
    """Every regular file under ``root`` in a stable, sorted order."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_file():
                found.append(p)
    return found


def parse_file(rel: str, raw: bytes, sha: str, policy: Mapping[str, Any]) -> Item:
    """Pass A for one file: decode and parse (content beats extension), or quarantine."""
    ext = Path(rel).suffix.lower()
    if len(raw) > int(pol.get(policy, "ingest.max_file_mb", 512)) * 1024 * 1024:
        raise QuarantineError("file_too_large")
    fmt = detect_format(ext, pol.get(policy, "ingest.supported_extensions", ()))
    decoded = decode_bytes(raw)
    text = decoded.text
    if decoded.encoding == "cp1252" and fmt not in _LEGACY_OK:
        raise QuarantineError("undecodable_text")
    depth = int(pol.get(policy, "ingest.max_json_depth", 200))
    if fmt in ("csv", "tsv") and text.lstrip()[:1] in ("{", "["):
        try:
            data = load_json(text, depth)
            return Item(rel, sha, "json", data, _json_locs(data), infer_order(text) or "dmy")
        except QuarantineError:
            pass
    order = infer_order(text) or "dmy"
    if fmt in ("csv", "tsv"):
        header, rows = read_table(text, "\t" if fmt == "tsv" else ",")
        return Item(rel, sha, fmt, (header, rows), [f"row:{i}" for i in range(len(rows))], order)
    if fmt == "json":
        data = load_json(text, depth)
        return Item(rel, sha, fmt, data, _json_locs(data), order)
    return Item(rel, sha, "text", text, ["doc"], order)


def _json_locs(data: Any) -> list[str]:
    """``doc`` for the whole document, plus a pointer per record of any record collection."""
    ptrs = record_pointers(data)
    return ptrs if ptrs == ["doc"] else ["doc"] + ptrs


def _safe_dest(san: Path, rel: str) -> Path:
    dest = (san / rel).resolve()
    if san.resolve() not in dest.parents:
        raise QuarantineError("parse_error.path")
    return dest


def run(inp: Path, out: Path, policy: Mapping[str, Any], keys: Keyring) -> int:
    """Run the full pipeline from ``inp`` to ``out``; return the process exit code."""
    t0 = time.monotonic()
    san = out / "sanitized"
    san.mkdir(parents=True, exist_ok=True)
    report = RunReport()
    paths = walk_inputs(inp)
    LOG.emit("run.start", files=len(paths))

    # ---- Pass A: hash, decode, parse
    set_stage("ingest")
    entries: list[FileEntry] = []
    parsed: list[tuple[FileEntry, Item | None]] = []
    for path in paths:
        rel = path.relative_to(inp).as_posix()
        with open(path, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        entry = FileEntry(input_sha256=sha, status="quarantined")
        try:
            item: Item | None = parse_file(rel, raw, sha, policy)
        except QuarantineError as exc:
            entry.reason, item = exc.reason, None
        except Exception as exc:  # noqa: BLE001 - any failure quarantines, never crashes
            entry.reason, item = f"parse_error.{type(exc).__name__.lower()}", None
        entries.append(entry)
        parsed.append((entry, item))

    # ---- Pass A (cont.): learn the dataset, link records
    set_stage("learn")
    pipe = Pipeline(keys, policy)
    items = [it for _, it in parsed if it is not None]
    pipe.observe(items)
    pipe.learn(items)

    # ---- Pass B: rewrite
    set_stage("rewrite")
    used: set[str] = set()
    for entry, item in parsed:
        if item is None:
            continue
        try:
            text = pipe.rewrite(item)
            out_rel = pipe.output_path(item.rel)
            if out_rel in used:
                raise QuarantineError("parse_error.name_collision")
            dest = _safe_dest(san, out_rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            used.add(out_rel)
        except QuarantineError as exc:
            entry.reason = exc.reason
            continue
        except Exception as exc:  # noqa: BLE001
            entry.reason = f"parse_error.{type(exc).__name__.lower()}"
            continue
        entry.status, entry.output, entry.reason = "sanitized", f"sanitized/{out_rel}", None
        for loc in item.locs:
            r = rid(item.rel, loc)
            report.records.append(Record(file=entry.output, loc=loc, patient=pipe.psn.get(r),
                                         status="generalized" if r in pipe.generalized else None))

    set_stage("report")
    report.entities.update(pipe.entities)
    report.records_generalized = sum(r.status == "generalized" for r in report.records)
    for entry in entries:
        if entry.status == "quarantined":
            LOG.emit("file.quarantined", sha=sha_prefix(entry.input_sha256), reason=entry.reason)
    report.files = entries
    if len(report.files) != len(paths):
        LOG.emit("accounting.mismatch", inputs=len(paths), accounted=len(report.files))
        return 1
    seconds = time.monotonic() - t0
    report.write(out, seconds, peak_rss_mb())
    c = report.counts()
    LOG.emit("run.done", files=c["files_total"], sanitized=c["files_sanitized"],
             quarantined=c["files_quarantined"], records=c["records_processed"],
             linked=c["records_linked"], identifiers=c["identifiers_detected"],
             seconds=round(seconds, 2))
    return 0


class _QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # never echo argument values
        LOG.emit("args.invalid", problem="usage")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python main.py --input DIR --output DIR``."""
    install_guards()
    ap = _QuietParser(prog="anamika", description="Anamika privacy firewall")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    inp, out = Path(args.input).resolve(), Path(args.output).resolve()
    if not inp.is_dir():
        LOG.emit("args.invalid", problem="input_not_a_directory")
        return 2
    if out == inp or inp in out.parents:
        LOG.emit("args.invalid", problem="output_inside_input")
        return 2
    try:
        keys = Keyring.from_env()
    except SecretMissing:
        LOG.emit("secret.missing")
        return 2
    return run(inp, out, pol.load_policy(), keys)
