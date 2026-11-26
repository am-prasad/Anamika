"""Top-level runner: argument parsing, the guarded two-pass pipeline and exit codes.

Pass A reads, hashes, decodes and parses every input (collecting identity evidence in
later stages). Pass B rewrites each parsed file and writes it under ``sanitized/``.
Any failure in either pass quarantines that file with a closed-vocabulary reason; no
partial output is ever written. Exit code 0 is returned only when every input file is
accounted for in ``report.json``.

Exit codes: 0 complete release · 1 accounting failure or fatal error · 2 bad invocation
or missing secret.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import policy as pol
from .ingest.csv_io import read_table, write_table
from .ingest.json_io import dump_json, load_json, record_pointers
from .ingest.sniff import QuarantineError, decode_bytes, detect_format
from .report import FileEntry, Record, RunReport, peak_rss_mb
from .rewrite.text_out import clean_text, clean_value
from .safety import LOG, Keyring, SecretMissing, install_guards, set_stage, sha_prefix


@dataclass
class Parsed:
    """A fully parsed input file, ready for rewriting."""

    rel: str
    sha: str
    fmt: str  # csv | tsv | json | text
    payload: Any
    locs: list[str] = field(default_factory=list)


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


def parse_file(rel: str, raw: bytes, sha: str, policy: Mapping[str, Any]) -> Parsed:
    """Pass A for one file: decode and parse, or raise :class:`QuarantineError`."""
    ext = Path(rel).suffix.lower()
    if len(raw) > int(pol.get(policy, "ingest.max_file_mb", 512)) * 1024 * 1024:
        raise QuarantineError("file_too_large")
    fmt = detect_format(ext, pol.get(policy, "ingest.supported_extensions", ()))
    text = decode_bytes(raw).text
    if fmt in ("csv", "tsv"):
        header, rows = read_table(text, "\t" if fmt == "tsv" else ",")
        return Parsed(rel, sha, fmt, (header, rows), [f"row:{i}" for i in range(len(rows))])
    if fmt == "json":
        data = load_json(text, int(pol.get(policy, "ingest.max_json_depth", 200)))
        return Parsed(rel, sha, fmt, data, record_pointers(data))
    return Parsed(rel, sha, fmt, text, ["doc"])


def rewrite_file(item: Parsed, counts: Counter[str]) -> str:
    """Pass B for one file: return the sanitised text in the original format."""
    if item.fmt in ("csv", "tsv"):
        header, rows = item.payload
        clean_rows = [[clean_text(c, counts) for c in row] for row in rows]
        return write_table(header, clean_rows, "\t" if item.fmt == "tsv" else ",")
    if item.fmt == "json":
        return dump_json(clean_value(item.payload, counts))
    return clean_text(item.payload, counts)


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
    parsed: list[tuple[FileEntry, Parsed | None]] = []
    for path in paths:
        rel = path.relative_to(inp).as_posix()
        with open(path, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        entry = FileEntry(input_sha256=sha, status="quarantined")
        try:
            item: Parsed | None = parse_file(rel, raw, sha, policy)
        except QuarantineError as exc:
            entry.reason, item = exc.reason, None
        except Exception as exc:  # noqa: BLE001 - any failure quarantines, never crashes
            entry.reason, item = f"parse_error.{type(exc).__name__.lower()}", None
        entries.append(entry)
        parsed.append((entry, item))

    # ---- (linkage happens here from S2 on)
    set_stage("rewrite")
    for entry, item in parsed:
        if item is None:
            continue
        counts: Counter[str] = Counter()
        try:
            text = rewrite_file(item, counts)
            dest = _safe_dest(san, item.rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except QuarantineError as exc:
            entry.reason = exc.reason
            continue
        except Exception as exc:  # noqa: BLE001
            entry.reason = f"parse_error.{type(exc).__name__.lower()}"
            continue
        entry.status, entry.output, entry.reason = "sanitized", f"sanitized/{item.rel}", None
        report.entities.update(counts)
        for loc in item.locs:
            report.records.append(Record(file=entry.output, loc=loc, patient=None))

    set_stage("report")
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
