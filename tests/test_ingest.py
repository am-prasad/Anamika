"""Ingestion tests: decoding, depth guard, record pointers, quarantine reasons."""
from __future__ import annotations

import pytest

from anamika.ingest.csv_io import read_table, write_table
from anamika.ingest.json_io import load_json, max_depth, record_pointers
from anamika.ingest.sniff import QuarantineError, decode_bytes, detect_format

SUPPORTED = (".csv", ".tsv", ".json", ".txt")


@pytest.mark.parametrize("raw,enc", [
    ("नाम: रीता".encode("utf-8"), "utf-8"),
    (b"\xef\xbb\xbfName,Age\n", "utf-8-sig"),
    ("Naam\tUmar\nरीता\t45\n".encode("utf-16"), "utf-16"),
    ("Temp 101°F – stable".encode("cp1252"), "cp1252"),
])
def test_decode_known_encodings(raw: bytes, enc: str) -> None:
    assert decode_bytes(raw).encoding == enc


@pytest.mark.parametrize("raw,reason", [
    (b"", "empty_file"), (b"  \n", "empty_file"),
    (b"\x89PNG\r\n\x1a\n\x00\x00", "binary_content"),
    (b"\x81\x8d\x8f\x90\x9d" * 3, "undecodable_text"),
])
def test_decode_quarantines(raw: bytes, reason: str) -> None:
    with pytest.raises(QuarantineError) as ei:
        decode_bytes(raw)
    assert ei.value.reason == reason and str(ei.value) == reason


@pytest.mark.parametrize("ext", [".pdf", ".jpg", ".xml", ".xlsx", ".zip", ""])
def test_unsupported_extensions(ext: str) -> None:
    with pytest.raises(QuarantineError):
        detect_format(ext, SUPPORTED)


def test_quarantine_reason_is_closed_vocabulary() -> None:
    assert QuarantineError("Ramesh Kumar leaked").reason == "parse_error.unknown"


def test_depth_guard_quarantines_deep_json() -> None:
    deep = "[" * 1500 + "]" * 1500
    assert max_depth(deep) == 1500
    with pytest.raises(QuarantineError) as ei:
        load_json(deep, 200)
    assert ei.value.reason == "json_too_deep"


def test_depth_guard_ignores_brackets_in_strings() -> None:
    assert max_depth('{"note": "[[[[{{{{"}') == 1


@pytest.mark.parametrize("text", ['{"visits": [{"patient": "x", "mob', "{", '{"a": }'])
def test_truncated_json_is_malformed(text: str) -> None:
    with pytest.raises(QuarantineError) as ei:
        load_json(text, 200)
    assert ei.value.reason == "malformed_json"


def test_record_pointers() -> None:
    assert record_pointers({"meta": {}, "visits": [{}, {}]}) == ["/visits/0", "/visits/1"]
    assert record_pointers({"resourceType": "Bundle", "entry": [{}, {}]}) == ["doc"]
    assert record_pointers({"patient": {"name": "x"}}) == ["doc"]
    assert record_pointers({"a/b": [{}]}) == ["/a~1b/0"]


def test_csv_roundtrip_keeps_quoted_newlines() -> None:
    text = 'ID,Notes\nA1,"line one\nline two"\nA2,ok\n'
    header, rows = read_table(text, ",")
    assert header == ["ID", "Notes"] and len(rows) == 2
    assert write_table(header, rows, ",") == text
