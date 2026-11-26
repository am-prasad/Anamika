"""Detection tests on invented, synthetic strings: patterns, columns, context, meaning traps."""
from __future__ import annotations

import pytest

from anamika.detect import columns as C
from anamika.detect.engine import Detector
from anamika.detect.patterns import RULES, ascii_digits, phone_key, verhoeff_valid
from anamika.detect.runtime import RuntimeLexicon


def lex_with(*names: str, ids: tuple[str, ...] = (), places: tuple[str, ...] = (),
             text: str = "") -> RuntimeLexicon:
    lx = RuntimeLexicon()
    for n in names:
        lx.add_name(n)
    for i in ids:
        lx.add_id(i)
    for p in places:
        lx.add_place(p)
    lx.observe_text(text or "patient admitted with fever and cough for review in the ward")
    lx.compile()
    return lx


def found(text: str, lx: RuntimeLexicon | None = None, mode: str = "text") -> list[tuple[str, str]]:
    d = Detector(lx or lex_with())
    return [(s.etype, text[s.start:s.end]) for s in d.detect(text, mode)]


def types(text: str, lx: RuntimeLexicon | None = None) -> set[str]:
    return {t for t, _ in found(text, lx)}


# ------------------------------------------------------------------ patterns

@pytest.mark.parametrize("text", ["Mob: +91 98765 43210", "call 098765-43210", "ph 9876543210",
                                  "मोबाइल: ९८७६५४३२१०", "+91-9876543210 (home)"])
def test_phone_formats(text: str) -> None:
    assert "PHONE" in types(text)


@pytest.mark.parametrize("text", ["Dolo 650 BD x 5 days", "Tab Amlodipine 5 mg 1-0-1", "BP 117/82, Pulse 88/min",
                                  "Platelet 145000 /uL", "SpO2 96%", "Hb 10.2 g/dL (12.0-15.5)",
                                  "Admitted 03-10-2026", "ICD N18.3, LOINC 2345-7"])
def test_clinical_numbers_are_not_pii(text: str) -> None:
    assert types(text) == set()


@pytest.mark.parametrize("text,etype", [("Aadhaar 2345 6789 0123", "AADHAAR"),
                                        ("UID 234567890123", "AADHAAR"),
                                        ("ABHA 91-2345-6789-0123", "ABHA_NUMBER"),
                                        ("xxxx xxxx 4821", "AADHAAR_MASKED"),
                                        ("PAN ABCPD1234K", "PAN"),
                                        ("mail a.b@example.org", "EMAIL"),
                                        ("id test.user@abdm", "ABHA_ADDRESS"),
                                        ("Pin Code: 226010", "PIN")])
def test_identifier_patterns(text: str, etype: str) -> None:
    assert etype in types(text)


def test_digit_helpers() -> None:
    assert ascii_digits("९८७") == "987"
    assert phone_key("+91 98765 43210") == "9876543210"
    assert phone_key("12345") is None
    assert verhoeff_valid("2363") and len(RULES) >= 9


# ------------------------------------------------------------------ columns

@pytest.mark.parametrize("header,role", [
    ("Patient Name", C.PATIENT_NAME), ("Naam", C.PATIENT_NAME), ("मरीज़ का नाम", C.PATIENT_NAME),
    ("Pita/Pati ka Naam", C.RELATIVE_NAME), ("Father's Name", C.RELATIVE_NAME),
    ("Gaon", C.VILLAGE), ("Jila", C.DISTRICT), ("Tehsil", C.TEHSIL), ("Umar", C.AGE),
    ("Janm Tithi", C.DOB), ("DOB (MM/DD/YYYY)", C.DOB), ("Contact#", C.PHONE), ("Mobile No", C.PHONE),
    ("UHID", C.MRN), ("patient_ref", C.MRN), ("Aadhar", C.AADHAAR), ("Pin Code", C.PIN),
    ("ref_doctor", C.DOCTOR), ("Reg Date", C.DATE), ("Ling", C.GENDER),
])
def test_header_synonyms(header: str, role: str) -> None:
    assert C.classify_label(header) == role


@pytest.mark.parametrize("values,role", [
    (["9876543210", "8123456789", "7012345678"], C.PHONE),
    (["2345 6789 0123", "3456 7890 1234"], C.AADHAAR),
    (["a@x.org", "b@y.in", "c@z.com"], C.EMAIL),
    (["226010", "229073", "262701"], C.PIN),
])
def test_value_profiling_handles_unseen_headers(values: list[str], role: str) -> None:
    assert C.classify_column("col_17", values) == role


def test_date_order_hint() -> None:
    assert C.date_order_hint("Registered (MM/DD/YYYY)") == "mdy"
    assert C.date_order_hint("DOB (DD-MM-YYYY)") == "dmy"


# ------------------------------------------------------------------ context & meaning traps

@pytest.mark.parametrize("text,name", [
    ("Patient Name: Zorawar Pundir   Age/Sex: 52 Yrs/M", "Zorawar Pundir"),
    ("Name: Bhavika Tandel   Age: 34/F", "Bhavika Tandel"),
    ("नाम: रुक्मिणी चौहान   आयु: 47 वर्ष", "रुक्मिणी चौहान"),
    ("मरीज़ का नाम: हरप्रीत कौर", "हरप्रीत कौर"),
])
def test_patient_labels_en_hi(text: str, name: str) -> None:
    assert ("PATIENT_NAME", name) in found(text)


@pytest.mark.parametrize("text", ["S/o Kesar Pundir", "W/o Ilavarasan Nair", "D/O Tejpal Gurjar",
                                  "पुत्र बलवंत सिंह", "Attendant: Omkar Tandel, Mob. 9876543210"])
def test_relatives(text: str) -> None:
    assert "RELATIVE_NAME" in types(text)


@pytest.mark.parametrize("text", ["C/O fever x 3 days", "C/O: pain abdomen", "K/C/O DM2 x 5 yrs",
                                  "K/C/O addison's disease", "H/O TB 5 yrs back"])
def test_complaints_and_history_are_kept(text: str) -> None:
    assert types(text) == set()


def test_care_of_a_person_is_relative() -> None:
    assert ("RELATIVE_NAME", "Kesar Pundir") in found("C/O Kesar Pundir, H.No. 12")


@pytest.mark.parametrize("text", ["Consultant: Dr. Kesar Pundir (MD Medicine)",
                                  "Review in OPD with Dr. Kesar Pundir.", "डॉ. केसर पुंडीर"])
def test_doctors_are_kept_even_when_name_is_known(text: str) -> None:
    lx = lex_with("Kesar Pundir", "केसर पुंडीर")
    assert not any(t in ("PATIENT_NAME", "PERSON_NAME", "RELATIVE_NAME") for t in types(text, lx))


def test_doctor_vs_relative_same_first_name() -> None:
    lx = lex_with("Kesar Pundir")
    text = "S/o Kesar Pundir. Seen by Dr. Kesar Mathur."
    f = found(text, lx)
    assert ("RELATIVE_NAME", "Kesar Pundir") in f
    assert all("Mathur" not in v for _, v in f)


@pytest.mark.parametrize("text,name", [
    ("Zorawar sahab ka BP 150/90", "Zorawar"),
    ("Bhavika ji 34 Y / F", "Bhavika"),
    ("Zorawar Pundir ki condition stable hai", "Zorawar Pundir"),
    ("रुक्मिणी जी को बुखार है", "रुक्मिणी"),
])
def test_hinglish_honorifics_and_particles(text: str, name: str) -> None:
    lx = lex_with(text="bp ki condition stable hai ka ko ne")
    assert any(name in v for t, v in found(text, lx) if t in ("PERSON_NAME", "PATIENT_NAME"))


@pytest.mark.parametrize("text", ["K/C/O Parkinson's disease", "Graves disease, controlled",
                                  "Wilson's disease on penicillamine"])
def test_eponyms_survive_even_for_a_patient_with_that_surname(text: str) -> None:
    lx = lex_with("Ravi Parkinson", "Asha Graves", "Tom Wilson")
    assert types(text, lx) == set()


@pytest.mark.parametrize("text", ["Jeevan Jyoti Charitable Hospital, Barabanki",
                                  "*Lifeline Pathology*", "SANJIVANI MULTISPECIALITY HOSPITAL"])
def test_facilities_are_kept(text: str) -> None:
    lx = lex_with("Jyoti Verma", "Sanjivani Rao")
    assert not types(text, lx) & {"PERSON_NAME", "PATIENT_NAME"}


def test_address_keeps_tehsil_and_district() -> None:
    text = "Address: H.No. 12, Mohalla Qila, near Pani Tanki, Tehsil Lalganj, Distt. Rae Bareli - 229206"
    f = found(text)
    kept = text
    for _, v in f:
        kept = kept.replace(v, "")
    assert "Tehsil Lalganj" in kept and "Distt. Rae Bareli" in kept
    assert ("PIN", "229206") in f and "Pani Tanki" not in kept


@pytest.mark.parametrize("text", ["Surgical consent witnessed by Ojaswini Rathore",
                                  "called by Fatehjit Sodhi", "[12/10/26, 4:15 pm] Charulata Bisht: ok"])
def test_unseen_names_from_context(text: str) -> None:
    assert types(text) & {"PERSON_NAME", "PATIENT_NAME"}


def test_lexicon_finds_names_and_ids_in_hidden_channels() -> None:
    lx = lex_with("Bhavika Tandel", ids=("SNJ/26/000123", "IPD-2026-00042"))
    assert {"PERSON_NAME", "MRN"} <= types("D:\\HIS\\exports\\Bhavika_Tandel_000123\\v.json", lx)
    assert "MRN" in {t for t, _ in found("nursing_ipd-2026-00042", lx, "name")}
    assert "PERSON_NAME" in {t for t, _ in found("bhavika_tandel_report", lx, "name")}


def test_all_caps_acronym_not_taken_for_a_name() -> None:
    lx = lex_with("Asha Kumari")
    assert types("Referred by ASHA worker", lx) == set()
