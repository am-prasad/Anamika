"""``report.json`` and ``records.jsonl`` writers with counts computed from real work.

Counts are derived from the file entries and record lines actually written, never
estimated, because the organisers cross-check them against the export.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "raksha-report/1"


@dataclass
class FileEntry:
    """One input file's fate. Identified only by SHA-256, never by name."""

    input_sha256: str
    status: str  # sanitized | quarantined | suppressed
    output: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"input_sha256": self.input_sha256, "output": self.output,
                             "status": self.status}
        if self.reason:
            d["reason"] = self.reason
        return d


@dataclass
class Record:
    """One exported patient-bearing record (a line of ``records.jsonl``)."""

    file: str
    loc: str
    patient: str | None
    out: str | None = None
    status: str | None = None
    rid_key: str = field(default="", repr=False, compare=False)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"file": self.file, "loc": self.loc, "patient": self.patient}
        if self.out is not None and self.out != self.loc:
            d["out"] = self.out
        if self.status:
            d["status"] = self.status
        return d


@dataclass
class RunReport:
    """Accumulates file entries, records and entity counts for one run."""

    files: list[FileEntry] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    entities: Counter[str] = field(default_factory=Counter)
    records_generalized: int = 0
    records_suppressed: int = 0

    def counts(self) -> dict[str, int]:
        """Counts recomputed from the entries and records actually exported."""
        sanitized = sum(f.status == "sanitized" for f in self.files)
        quarantined = sum(f.status == "quarantined" for f in self.files)
        return {
            "files_total": len(self.files),
            "files_sanitized": sanitized,
            "files_quarantined": quarantined,
            "records_processed": len(self.records),
            "identifiers_detected": int(sum(self.entities.values())),
            "records_linked": sum(r.patient is not None for r in self.records),
            "records_generalized": self.records_generalized,
            "records_suppressed": self.records_suppressed,
            "records_quarantined": 0,
        }

    def build(self, seconds: float, peak_rss_mb: float) -> dict[str, Any]:
        """The ``report.json`` document."""
        return {
            "schema": SCHEMA,
            "files": [f.as_dict() for f in self.files],
            "counts": self.counts(),
            "entities": dict(sorted(self.entities.items())),
            "timing": {"seconds": round(seconds, 2)},
            "resources": {"peak_rss_mb": round(peak_rss_mb, 1)},
        }

    def write(self, out_dir: Path, seconds: float, peak_rss_mb: float) -> None:
        """Write ``records.jsonl`` then ``report.json`` into ``out_dir``."""
        with open(out_dir / "records.jsonl", "w", encoding="utf-8", newline="\n") as fh:
            for r in self.records:
                fh.write(json.dumps(r.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        doc = self.build(seconds, peak_rss_mb)
        (out_dir / "report.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def peak_rss_mb() -> float:
    """Peak resident set size of this process and its children, in MB."""
    try:
        import resource

        self_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        child_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        scale = 1024 * 1024 if sys.platform == "darwin" else 1024
        return (self_kb + child_kb) / scale
    except (ImportError, OSError):
        try:
            import psutil

            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:  # noqa: BLE001 - best effort only
            return 0.0
