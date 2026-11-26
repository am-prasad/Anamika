"""Structured field classifier: CSV headers and JSON keys → semantic roles.

Two signals are combined:

1. **Header / key synonyms** in English, Hinglish transliteration and Devanagari
   (``Patient Name``, ``Naam``, ``मरीज़ का नाम``, ``Pita/Pati ka Naam``, ``Gaon``, ``Jila``…),
   matched on a normalised form so ``Patient's Name``, ``patient_name`` and ``PATIENT NAME``
   agree.
2. **Value profiling** for unknown headers: the share of values that look like phones,
   Aadhaar, ABHA, e-mail, PAN, PINs, dates or hospital identifiers. Hidden datasets rename
   columns; values keep their shape.

Roles decide the action in :mod:`anamika.rewrite`: replace (names, IDs, contacts),
generalise (age, DOB, village, PIN, dates), keep (gender, tehsil, district, clinical), or
scan as free text.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

from .patterns import EMAIL_RX, PHONE_RX, ascii_digits

# Roles
PATIENT_NAME, FIRST_NAME, LAST_NAME, LOCAL_NAME = "patient_name", "first_name", "last_name", "local_name"
RELATIVE_NAME, RELATION, GUARDIAN = "relative_name", "relation", "guardian"
ADDRESS, VILLAGE, LOCALITY, HOUSE = "address", "village", "locality", "house"
TEHSIL, DISTRICT, STATE, PIN = "tehsil", "district", "state", "pin"
PHONE, EMAIL, AADHAAR, ABHA, ABHA_ADDRESS, PAN = "phone", "email", "aadhaar", "abha", "abha_address", "pan"
MRN, INSURANCE, DOB, AGE, AGE_SEX, GENDER, DATE = "mrn", "insurance", "dob", "age", "age_sex", "gender", "date"
DOCTOR, FACILITY, PERSON_NAME, TEXT, KEEP = "doctor", "facility", "person_name", "text", "keep"

#: roles whose value is replaced outright
REPLACE_ROLES = {PATIENT_NAME, FIRST_NAME, LAST_NAME, LOCAL_NAME, RELATIVE_NAME, GUARDIAN,
                 PERSON_NAME, PHONE, EMAIL, AADHAAR, ABHA, ABHA_ADDRESS, PAN, MRN, INSURANCE,
                 HOUSE, LOCALITY}
NAME_ROLES = {PATIENT_NAME, FIRST_NAME, LAST_NAME, LOCAL_NAME, RELATIVE_NAME, GUARDIAN, PERSON_NAME}

# Ordered: first match wins. Each entry: (role, exact-normalised names, substrings).
_SYNONYMS: list[tuple[str, set[str], tuple[str, ...]]] = [
    (DOB, {"dob", "dateofbirth", "birthdate", "janmtithi", "जन्मतिथि", "birthday", "dobmmddyyyy",
           "dobddmmyyyy"}, ("dateofbirth", "birthdate", "janmtithi", "जन्म")),
    (AGE_SEX, {"agesex", "agegender", "ageandsex"}, ()),
    (ABHA_ADDRESS, {"abhaaddress", "healthidaddress", "phraddress"}, ()),
    (ABHA, {"abha", "abhano", "abhanumber", "abhaid", "healthid", "healthidno", "ndhmid"}, ("abha",)),
    (AADHAAR, {"aadhaar", "aadhar", "aadhaarno", "aadharno", "aadhaarnumber", "uid", "uidai",
               "आधार"}, ("aadhaar", "aadhar", "adhaar", "aadhr", "आधार")),
    (PAN, {"pan", "panno", "pancard", "payerpan", "pannumber"}, ("pancard",)),
    (EMAIL, {"email", "emailid", "mail", "eml"}, ("email",)),
    (INSURANCE, {"policy", "policyno", "policynumber", "insuranceid", "insuranceno", "memberid",
                 "tpaid", "cardno", "pmjayid", "claimid", "schemeid"}, ("policy", "insurance")),
    (MRN, {"uhid", "mrn", "mrno", "crno", "regno", "registrationno", "registrationnumber", "regnno",
           "patientid", "patientref", "patref", "hospitaluhid", "hospitalid", "ipno", "ipdno",
           "admno", "admissionno", "caseno", "pid", "पंजीकरणसं", "पंजीकरणसंख्या", "uhidno"},
     ("uhid", "mrn", "patientref", "patientid", "registrationno", "पंजीकरण")),
    (RELATIVE_NAME, {"relativename", "guardianname", "fathername", "husbandname", "mothername",
                     "fatherhusbandname", "pitapatikanaam", "pitakanaam", "patikanaam", "nok",
                     "nextofkin", "attendant", "attendantname", "careof", "co", "spouse",
                     "पिताकानाम", "पतिकानाम", "पितापतिकानाम", "relative", "kin", "informant"},
     ("relativename", "guardianname", "fathername", "husbandname", "pitapati", "attendant",
      "पिता", "पति")),
    (GUARDIAN, {"guardian", "fatherhusband"}, ()),
    (RELATION, {"relation", "relationship", "rel", "relationtype", "sambandh", "संबंध"}, ()),
    (FIRST_NAME, {"firstname", "fname", "givenname", "given", "first"}, ("firstname",)),
    (LAST_NAME, {"lastname", "lname", "surname", "familyname", "family", "last"}, ("lastname", "surname")),
    (LOCAL_NAME, {"local", "localname", "namelocal", "hindiname", "namehindi", "नामहिंदी"}, ()),
    (DOCTOR, {"doctor", "refdoctor", "referringdoctor", "consultant", "referredby", "refby",
              "physician", "treatingdoctor", "attendingdoctor", "surgeon", "author"},
     ("doctor", "consultant", "referredby", "physician")),
    (FACILITY, {"facility", "hospital", "hospitalname", "lab", "labname", "clinic", "centre"}, ()),
    (PATIENT_NAME, {"name", "patientname", "ptname", "naam", "patient", "patientsname", "fullname",
                    "नाम", "मरीज़कानाम", "मरीजकानाम", "रोगीकानाम", "beneficiaryname", "insuredname",
                    "claimantname"}, ("patientname", "ptname", "मरीज़", "रोगी")),
    (PHONE, {"mobile", "mob", "mobileno", "mobilenumber", "phone", "phoneno", "contact", "contactno",
             "tel", "telephone", "callback", "whatsapp", "मोबाइल", "फोन", "cell"},
     ("mobile", "phone", "contactno", "callback", "मोबाइल")),
    (PIN, {"pin", "pincode", "zip", "zipcode", "postalcode", "postcode", "पिन", "पिनकोड"},
     ("pincode", "postal", "zip")),
    (HOUSE, {"house", "houseno", "hno", "housenumber", "makan", "मकान"}, ()),
    (LOCALITY, {"locality", "mohalla", "colony", "street", "landmark", "moholla", "basti"}, ()),
    (VILLAGE, {"village", "villagemohalla", "gaon", "gram", "ग्राम", "गांव", "गाँव", "city", "town",
               "villagetown", "vill"}, ("village", "gaon")),
    (TEHSIL, {"tehsil", "taluka", "taluk", "block", "तहसील", "subdistrict", "tehsilname"}, ("tehsil",)),
    (DISTRICT, {"district", "jila", "zila", "distt", "dist", "जिला", "ज़िला", "districtname"}, ("district",)),
    (STATE, {"state", "pradesh", "राज्य", "country"}, ()),
    (ADDRESS, {"address", "addr", "pata", "पता", "street", "line", "addressline", "residence",
               "permanentaddress", "fulladdress"}, ("address", "पता")),
    (AGE, {"age", "umar", "उम्र", "आयु", "ageyears", "ageyrs", "ageinyears"}, ()),
    (GENDER, {"gender", "sex", "ling", "लिंग"}, ()),
]

_DATE_HINTS = ("date", "dated", "time", "tithi", "तारीख", "collected", "reported", "registered",
               "visit", "admission", "discharge", "admitted", "discharged", "dt", "doa", "dod",
               "generated", "exported", "timestamp", "on")


def normalise_label(label: str) -> str:
    """Lower-case, NFC, drop bracketed hints and everything but letters/digits."""
    s = unicodedata.normalize("NFC", label or "")
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace("'s", "").replace("’s", "")
    s = re.sub(r"[^\wऀ-ॿ]+", "", s.casefold())
    return s.replace("_", "")


def classify_label(label: str) -> str | None:
    """Role for a header / key, or ``None`` when the name alone is not conclusive."""
    n = normalise_label(label)
    if not n:
        return None
    for role, exact, subs in _SYNONYMS:
        if n in exact:
            return role
    for role, _exact, subs in _SYNONYMS:
        if any(s in n for s in subs):
            return role
    raw = (label or "").casefold()
    tokens = re.split(r"[^a-zऀ-ॿ]+", raw)
    if any(t in _DATE_HINTS for t in tokens) or n.endswith(("date", "dt", "on", "at")):
        return DATE
    return None


def date_order_hint(label: str) -> str | None:
    """``mdy`` / ``dmy`` when the header states the format (``DOB (MM/DD/YYYY)``)."""
    up = (label or "").upper()
    if "MM/DD" in up or "MM-DD" in up:
        return "mdy"
    if "DD/MM" in up or "DD-MM" in up:
        return "dmy"
    return None


# --------------------------------------------------------------------------- value profiling

_AADHAAR = re.compile(r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}$")
_ABHA = re.compile(r"^\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_PIN = re.compile(r"^[1-8]\d{5}$")
_DATE = re.compile(r"^\d{1,4}[/.-]\d{1,2}[/.-]\d{2,4}(?:[T ][\d:.+\-Z]+)?$")
_ID = re.compile(r"^(?=.*\d)(?=.*[A-Za-z])[A-Za-z0-9]{1,8}(?:[/-][A-Za-z0-9]{1,10}){1,3}$|^[A-Z]{2,6}\d{5,}$")


def profile_values(values: Sequence[str]) -> str | None:
    """Infer a role from cell values alone (≥ 70% of non-empty cells must agree)."""
    vals = [ascii_digits(v).strip() for v in values if v and v.strip()]
    if len(vals) < 2:
        return None
    n = len(vals)

    def share(pred) -> float:  # type: ignore[no-untyped-def]
        return sum(1 for v in vals if pred(v)) / n

    checks = [
        (EMAIL, lambda v: bool(EMAIL_RX.fullmatch(v))),
        (ABHA, lambda v: bool(_ABHA.match(v)) and len(re.sub(r"\D", "", v)) == 14),
        (AADHAAR, lambda v: bool(_AADHAAR.match(v))),
        (PHONE, lambda v: bool(PHONE_RX.fullmatch(v))),
        (PAN, lambda v: bool(_PAN.match(v))),
        (PIN, lambda v: bool(_PIN.match(v))),
        (DATE, lambda v: bool(_DATE.match(v))),
    ]
    for role, pred in checks:
        if share(pred) >= 0.7:
            return role
    return None


def looks_like_id(value: str) -> bool:
    """Hospital-identifier shape: letters + digits with separators (``SNJ/26/064127``)."""
    return bool(_ID.match(value.strip()))


def classify_column(header: str, values: Iterable[str]) -> str:
    """Final role of a CSV column: header synonym, then value profile, else free text."""
    role = classify_label(header)
    vals = list(values)
    prof = profile_values(vals)
    if role is None:
        return prof or TEXT
    if role == DATE and prof not in (None, DATE):
        return prof
    return role
