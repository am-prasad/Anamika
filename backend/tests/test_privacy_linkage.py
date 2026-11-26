"""Date shifting, age bands, linkage constraints and an end-to-end run on synthetic data."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from anamika.link.cluster import Evidence, Linker, canonical_name
from anamika.privacy.ages import band_text, band_value
from anamika.privacy.dates import find_dates, infer_order, parse_date, shift_text
from anamika.privacy.location import pin_prefix

REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ dates

@pytest.mark.parametrize("text,expected", [
    ("Admitted 03-10-2026", "Admitted 12-11-2026"),
    ("DOB: 04/12/1977", "DOB: 13/01/1978"),
    ("2026-10-06T09:30:00+05:30", "2026-11-15T09:30:00+05:30"),
    ("[2/10/26, 4:15 pm]", "[11/11/26, 4:15 pm]"),
    ("12 Mar 2023", "21 Apr 2023"),
    ("Visit: 5 September", "Visit: 15 October"),
])
def test_dates_shift_in_original_format(text: str, expected: str) -> None:
    assert shift_text(text, 40)[0] == expected


def test_length_of_stay_is_exact() -> None:
    text = "Date of Admission: 28/02/2026\nDate of Discharge: 09/03/2026"
    out, n = shift_text(text, -123)
    a, b = [h.value for h in find_dates(out)]
    assert n == 2 and (b - a).days == 9


def test_month_first_inference() -> None:
    assert infer_order("01/25/1980, 03/14/2026") == "mdy"
    assert parse_date("03/04/2026", "mdy") == dt.date(2026, 3, 4)
    assert parse_date("03/04/2026", "dmy") == dt.date(2026, 4, 3)


@pytest.mark.parametrize("text", ["BP 117/82", "1-0-1 x 5 days", "Hb 12.0-15.5", "Version 3.1"])
def test_non_dates_untouched(text: str) -> None:
    assert shift_text(text, 40) == (text, 0)


# ------------------------------------------------------------------ ages & location

@pytest.mark.parametrize("text,expected", [
    ("Age/Sex: 48 Yrs/M", "Age/Sex: 45-49 Yrs/M"), ("आयु: 47 वर्ष", "आयु: 45-49 वर्ष"),
    ("x, 61 yrs, female", "x, 60-64 yrs, female"), ("Age: 97", "Age: 90+"),
    ("Chronic kidney disease, stage 3", "Chronic kidney disease, stage 3"),
    ("K/C/O DM2 x 12 yrs", "K/C/O DM2 x 12 yrs"),
])
def test_age_bands_are_truthful(text: str, expected: str) -> None:
    assert band_text(text)[0] == expected


def test_band_values_and_pins() -> None:
    assert band_value("48") == "45-49" and band_value("48 वर्ष") == "45-49 वर्ष"
    assert band_value("48/F") == "45-49/F" and band_value("abc") is None
    assert pin_prefix("229073") == "229***" and pin_prefix("12") is None


# ------------------------------------------------------------------ linkage

def ev(rid: str, *keys: str, **attrs: str) -> Evidence:
    e = Evidence(rid, set(keys))
    for k, v in attrs.items():
        e.attr(k, v)
    return e


def test_shared_identifier_links_across_hospitals() -> None:
    lk = Linker()
    lk.add(ev("a", "mrn:SNJ/26/1", "ph:9876543210"))
    lk.add(ev("b", "mrn:JJH-1"))
    lk.add(ev("c", "ph:9876543210", "mrn:JJH-1"))
    res = lk.solve()
    assert res["a"] == res["b"] == res["c"] is not None


def test_homonyms_with_different_dob_never_merge() -> None:
    lk = Linker()
    name = canonical_name("Md. Zorawar Pundir")
    a = ev("a", "mrn:A1", dob="1970-01-01")
    a.name = name
    b = ev("b", "mrn:B1", dob="1985-05-05")
    b.name = name
    lk.add(a)
    lk.add(b)
    res = lk.solve()
    assert res["a"] != res["b"]


def test_conflicting_aadhaar_blocks_transitive_merge() -> None:
    lk = Linker()
    lk.add(ev("a", "ph:9876543210", aadhaar="111122223333"))
    lk.add(ev("b", "ph:9876543210", aadhaar="444455556666"))
    res = lk.solve()
    assert res["a"] != res["b"]


def test_name_plus_dob_links_without_ids() -> None:
    lk = Linker()
    a, b = ev("a", dob="1970-01-01"), ev("b", dob="1970-01-01")
    a.name = canonical_name("Zorawar Pundir")
    b.name = canonical_name("PUNDIR ZORAWAR")
    lk.add(a)
    lk.add(b)
    res = lk.solve()
    assert res["a"] == res["b"] is not None


def test_no_evidence_means_no_link() -> None:
    lk = Linker()
    lk.add(ev("a"))
    assert lk.solve() == {"a": None}


# ------------------------------------------------------------------ end to end

NAMES = ["Zorawar Pundir", "Bhavika Tandel", "Kesar Pundir", "रुक्मिणी चौहान"]
PHONE, UHID = "9876501234", "QXH/26/550011"


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    inp = tmp_path / "input"
    (inp / "registration").mkdir(parents=True)
    (inp / "notes").mkdir()
    (inp / "lab").mkdir()
    (inp / "registration" / "reg.csv").write_text(
        "UHID,Patient Name,Gender,Age,DOB,Relative Name,Village,Tehsil,District,PIN,Mobile,Reg Date\n"
        f"{UHID},Zorawar Pundir,M,52,04/12/1973,S/o Kesar Pundir,Rampura Khas,Lalganj,Rae Bareli,229206,"
        f"{PHONE},03/10/2026\n", encoding="utf-8")
    (inp / "notes" / f"nursing_{UHID.replace('/', '-')}.txt").write_text(
        f"UHID: {UHID}\nDate of Admission: 03-10-2026\nDate of Discharge: 12-10-2026\n"
        "Zorawar sahab ka BP 150/90. Paracetamol 650 mg 1-0-1 x 5 days.\n"
        "Attendant: Kesar Pundir. Seen by Dr. Bhavika Tandel (MD Medicine).\n", encoding="utf-8")
    (inp / "lab" / f"{PHONE}_report.json").write_text(json.dumps(
        {"lab": "Lifeline Pathology", "patient": {"name": "Zorawar Pundir", "age": 52, "phone": PHONE,
                                                  "hospital_uhid": UHID},
         "collected": "2026-10-04T09:00:00+05:30",
         "panels": [{"name": "Routine", "results": [{"test": "Haemoglobin", "value": 13.1}]}]}),
        encoding="utf-8")
    (inp / "notes" / "hindi.txt").write_text("नाम: रुक्मिणी चौहान   आयु: 47 वर्ष\nतारीख: 05/10/2026\n",
                                             encoding="utf-8")
    return inp


def run(inp: Path, out: Path, secret: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, RAKSHA_SECRET=secret)
    return subprocess.run([sys.executable, str(REPO / "main.py"), "--input", str(inp), "--output", str(out)],
                          env=env, capture_output=True, text=True)


def test_end_to_end_release(dataset: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    p = run(dataset, out, "s1-test")
    assert p.returncode == 0
    blob = "\n".join(f.read_text(encoding="utf-8") + f.name for f in out.rglob("*") if f.is_file())
    for secret_value in NAMES[:2] + ["Rampura Khas", PHONE, UHID, "04/12/1973", "229206"]:
        if secret_value == "Bhavika Tandel":
            continue  # the doctor's name must survive
        assert secret_value not in blob, "leak"
    assert "Dr. Bhavika Tandel" in blob and "650 mg 1-0-1 x 5 days" in blob and "BP 150/90" in blob
    assert "Lalganj" in blob and "Rae Bareli" in blob and "229***" in blob and "50-54" in blob
    assert "रुक्मिणी" not in blob and "45-49 वर्ष" in blob
    records = [json.loads(line) for line in (out / "records.jsonl").read_text().splitlines()]
    psns = {r["patient"] for r in records if r["loc"] in ("row:0", "doc") and "hindi" not in r["file"]}
    psns.discard(None)
    assert len(psns) == 1, "registration, note and lab report must share one pseudonym"
    psn = psns.pop()
    for r in records:
        if r["patient"]:
            assert psn in (out / r["file"]).read_text(encoding="utf-8")
    note = next(out.rglob("nursing_*.txt")).read_text(encoding="utf-8")
    a, b = [h.value for h in find_dates(note)]
    assert (b - a).days == 9 and a != dt.date(2026, 10, 3)
    assert PHONE not in str(json.loads((out / "report.json").read_text()))


def test_secret_rotation_changes_pseudonyms_and_dates(dataset: Path, tmp_path: Path) -> None:
    run(dataset, tmp_path / "a", "secret-one")
    run(dataset, tmp_path / "b", "secret-two")
    run(dataset, tmp_path / "c", "secret-one")
    ra, rb, rc = ((tmp_path / x / "records.jsonl").read_text() for x in "abc")
    assert ra == rc and ra != rb
