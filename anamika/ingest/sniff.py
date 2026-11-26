"""Byte-level sniffing: decoding and format detection.

Decoding order: UTF-8 BOM → UTF-16 BOM → strict UTF-8 → strict cp1252. Anything else is
quarantined as ``undecodable_text``. Format is decided from the extension and confirmed
against content (S1 adds full content sniffing for mislabelled files).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class QuarantineError(Exception):
    """Raised when a file must be quarantined. ``reason`` is a closed-vocabulary identifier.

    The exception never carries file content: ``str(exc)`` is always the reason code.
    """

    REASONS = frozenset({
        "unsupported_format", "empty_file", "undecodable_text", "json_too_deep",
        "malformed_json", "malformed_table", "file_too_large", "binary_content",
    })

    def __init__(self, reason: str) -> None:
        if reason not in self.REASONS and not reason.startswith("parse_error."):
            reason = "parse_error.unknown"
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Decoded:
    """Decoded text plus the source encoding (for the report / debugging only)."""

    text: str
    encoding: str


def decode_bytes(raw: bytes) -> Decoded:
    """Decode ``raw`` to text or raise :class:`QuarantineError`."""
    if not raw.strip():
        raise QuarantineError("empty_file")
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return Decoded(raw[3:].decode("utf-8"), "utf-8-sig")
        except UnicodeDecodeError as exc:
            raise QuarantineError("undecodable_text") from exc
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return Decoded(raw.decode("utf-16"), "utf-16")
        except UnicodeDecodeError as exc:
            raise QuarantineError("undecodable_text") from exc
    if b"\x00" in raw[:4096]:
        raise QuarantineError("binary_content")
    for enc in ("utf-8", "cp1252"):
        try:
            return Decoded(raw.decode(enc), enc)
        except UnicodeDecodeError:
            continue
    raise QuarantineError("undecodable_text")


def detect_format(ext: str, supported: Iterable[str]) -> str:
    """Map a lower-case extension to ``csv | tsv | json | text`` or quarantine it."""
    if ext not in set(supported):
        raise QuarantineError("unsupported_format")
    return {".csv": "csv", ".tsv": "tsv", ".json": "json", ".txt": "text"}[ext]
