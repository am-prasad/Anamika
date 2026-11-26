"""S3: unseen text shapes, clinical-column safety, JSON tables, new IDs, debug export (synthetic)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from anamika.detect import columns as C
from anamika.detect.engine import Detector
from anamika.detect.runtime import RuntimeLexicon

REPO = Path(__file__).resolve().parents[1]


def det(*names: str, ids: tuple[str, ...] = ()) -> Detector:
    lx = RuntimeLexicon()
    for n in names:
        lx.add_name(n)
    for i in ids:
        lx.add_id(i)
    lx.observe_text("patient admitted with fever for review contact on bed")
    lx.compile()
    return Detector(lx)


def found(text: str, d: Detector | None = None) -> list[tuple[str, str]]:
    d = d or det()
    return [(s.etype, text[s.start:s.end]) for s in d.detect(text)]


@pytest.mark.parametrize("text,etype,value", [
    ("Pt admitted bed 4, contact son Arvind on call", "RELATIVE_NAME", "Arvind"),
    ("husband Tejpal came at 5 pm", "RELATIVE_NAME", "Tejpal"),
    ("बेटा राजू साथ है", "RELATIVE_NAME", "राजू"),
    ("मरीज़ रुक्मिणी चौहान को बुखार", "PATIENT_NAME", "रुक्मिणी चौहान"),
])
def test_kinship_and_patient_words(text: str, etype: str, value: str) -> None:
    assert (etype, value) in found(text)


def test_wife_of_is_not_kinship_name() -> None:
    assert ("RELATIVE_NAME", "of") not in found("Wife of Tejpal Gurjar")


@pytest.mark.parametrize("text,etype", [
    ("Sampark no - 9876501234", "PHONE"), ("Gaon - Rampura Khurd", "VILLAGE"),
    ("Mareez ka naam - Zorawar Pundir", "PATIENT_NAME"), ("Hospital No: QXH-5500112", "MRN"),
    ("OPD SLIP | Pt Name: Bhavika Tandel | Gram- Sohanpur", "VILLAGE"),
    ("<village>Sohanpur</village>", "VILLAGE"), ("<pt_name>Bhavika Tandel</pt_name>", "PATIENT_NAME"),
    ("referring her, resident of Sohanpur, for review", "VILLAGE"),
])
def test_any_known_label_works_in_text(text: str, etype: str) -> None:
    assert etype in {t for t, _ in found(text)}


@pytest.mark.parametrize("text", ["Diagnosis: Typhoid fever", "Ward/Bed: Ward 5 (Medicine) / Bed 12",
                                  "Advice: Low salt diet", "Consultant: Dr. Kamal Nayan Bajaj",
                                  "Visit: 5 September", "Sex: M"])
def test_non_pii_labels_untouched(text: str) -> None:
    assert not {t for t, _ in found(text)} & {"PATIENT_NAME", "PERSON_NAME", "VILLAGE", "MRN", "ADDRESS"}


def test_label_values_stop_at_column_gaps() -> None:
    text = "UHID: QXH/26/550011        IPD No: IPD-2026-00042"
    assert found(text) == [("MRN", "QXH/26/550011"), ("MRN", "IPD-2026-00042")]


@pytest.mark.parametrize("text,etype", [("call 98XXXXXX10", "PHONE"), ("ph 0522-2345678", "PHONE"),
                                        ("EPIC ABC1234567", "VOTER_ID")])
def test_new_identifier_patterns(text: str, etype: str) -> None:
    assert etype in {t for t, _ in found(text)}


@pytest.mark.parametrize("text", ["LOINC 2345-7", "ICD J45.909", "Sample S12345678", "Bill BL/26/004512"])
def test_new_patterns_do_not_hit_codes(text: str) -> None:
    assert found(text) == []


def test_possessive_name_is_found() -> None:
    assert ("PERSON_NAME", "Zorawar") in found("sample received from Zorawar's attendant", det("Zorawar Pundir"))


def test_embedded_ids_in_paths_and_file_names() -> None:
    d = det(ids=("IPD-2026-00042",))
    t = "exports/nursing_ipd-2026-00042.txt"
    assert [x for x in d.detect(t, "name") if x.etype == "MRN"]


# ------------------------------------------------------------------ clinical columns

@pytest.mark.parametrize("header", ["निदान", "Diagnosis", "Dx", "Complaint", "Drug", "Test Name"])
def test_clinical_headers_are_pinned(header: str) -> None:
    assert C.classify_label(header) == C.CLINICAL


def test_repeated_devanagari_category_is_not_a_name_column() -> None:
    assert C.profile_people_places(["मधुमेह", "मधुमेह", "मधुमेह"], lambda w: False) is None


# ------------------------------------------------------------------ end to end: JSON tables + debug

def run(inp: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, RAKSHA_SECRET="s3-test")
    return subprocess.run([sys.executable, str(REPO / "main.py"), "--input", str(inp), "--output", str(out), *extra],
                          env=env, capture_output=True, text=True)


def test_json_table_columns_are_applied_by_position(tmp_path: Path) -> None:
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "t.json").write_text(json.dumps({"columns": ["patient", "phone", "village", "dx"],
                                            "rows": [["Zorawar Pundir", "9876501234", "Sohanpur", "Asthma"],
                                                     ["Bhavika Tandel", "8765012349", "Rampura", "Anaemia"]]}))
    assert run(inp, tmp_path / "out").returncode == 0
    out = (tmp_path / "out" / "sanitized" / "t.json").read_text()
    for v in ("Zorawar", "9876501234", "Sohanpur", "Bhavika", "Rampura"):
        assert v not in out
    assert "Asthma" in out and "Anaemia" in out


def test_debug_spans_are_value_free_and_outside_output(tmp_path: Path) -> None:
    inp = tmp_path / "in"
    inp.mkdir()
    (inp / "n.txt").write_text("Name: Zorawar Pundir\nMob: 9876501234\nDolo 650 BD\n")
    out, dbg = tmp_path / "out", tmp_path / "dbg"
    assert run(inp, out, "--debug-spans", str(dbg)).returncode == 0
    files = [f for f in dbg.glob("*.json") if f.name != "linkage.json"]
    assert len(files) == 1 and "n.txt" not in files[0].name
    assert "Zorawar" not in (dbg / "linkage.json").read_text()
    blob = files[0].read_text()
    assert "Zorawar" not in blob and "9876501234" not in blob
    info = json.loads(blob)
    assert {s["type"] for s in info["spans"]} >= {"PATIENT_NAME", "PHONE"}
    assert run(inp, tmp_path / "o2", "--debug-spans", str(tmp_path / "o2" / "x")).returncode == 2
