"""CSV / TSV reading and writing with a stable, contract-preserving dialect.

Rows are read with the stdlib ``csv`` module (quoted newlines supported). Output uses
``\\n`` line endings and minimal quoting; the header is written unchanged unless the
rewrite layer renames a PII header.
"""
from __future__ import annotations

import csv
import io

from .sniff import QuarantineError


def read_table(text: str, delimiter: str) -> tuple[list[str], list[list[str]]]:
    """Parse ``text`` into ``(header, rows)``; raise :class:`QuarantineError` if impossible."""
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error as exc:
        raise QuarantineError("malformed_table") from exc
    if not rows:
        raise QuarantineError("empty_file")
    return rows[0], rows[1:]


def write_table(header: list[str], rows: list[list[str]], delimiter: str) -> str:
    """Serialise ``header`` and ``rows`` back to delimited text."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()
