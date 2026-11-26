"""Field-level rules shared by the CSV and JSON writers, and JSON role resolution.

A field's *role* (from :mod:`anamika.detect.columns`) decides its fate:

* replace — names → pseudonym / ``[NAME]`` / ``[RELATIVE]``; IDs → pseudonym / typed
  placeholder; contacts → ``[PHONE]``, ``[EMAIL]``…; house / locality → ``[ADDRESS]``;
* generalise — age → 5-year band, DOB and dates → per-patient shift, PIN → 3-digit
  prefix, village → tehsil;
* keep — gender, tehsil, district, state, relation, doctor, facility;
* free text — scanned by the text detector.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from ..detect import columns as C

PLACEHOLDER = {
    C.PHONE: "[PHONE]", C.EMAIL: "[EMAIL]", C.AADHAAR: "[AADHAAR]", C.ABHA: "[ABHA]",
    C.ABHA_ADDRESS: "[ABHA]", C.PAN: "[PAN]", C.INSURANCE: "[INSURANCE_ID]",
    C.HOUSE: "[ADDRESS]", C.LOCALITY: "[ADDRESS]", C.PERSON_NAME: "[NAME]",
    C.RELATIVE_NAME: "[RELATIVE]", C.GUARDIAN: "[RELATIVE]", C.LAST_NAME: "[NAME]",
}
ENTITY_OF_ROLE = {
    C.PATIENT_NAME: "PATIENT_NAME", C.FIRST_NAME: "PATIENT_NAME", C.LAST_NAME: "PATIENT_NAME",
    C.LOCAL_NAME: "PATIENT_NAME", C.RELATIVE_NAME: "RELATIVE_NAME", C.GUARDIAN: "RELATIVE_NAME",
    C.PERSON_NAME: "PERSON_NAME", C.PHONE: "PHONE", C.EMAIL: "EMAIL", C.AADHAAR: "AADHAAR",
    C.ABHA: "ABHA_NUMBER", C.ABHA_ADDRESS: "ABHA_ADDRESS", C.PAN: "PAN", C.MRN: "MRN",
    C.INSURANCE: "INSURANCE_ID", C.HOUSE: "HOUSE", C.LOCALITY: "LOCALITY", C.VILLAGE: "VILLAGE",
    C.PIN: "PIN", C.DOB: "DOB", C.ADDRESS: "ADDRESS",
}
_RELATION_PREFIX = re.compile(r"^\s*((?:S|D|W|C|H|F|M)\s*/\s*O\.?|Son of|Daughter of|Wife of|Care of|"
                              r"पुत्र|पुत्री|पत्नी|पति)\s*[:\-]?\s*", re.IGNORECASE)
_UUID = re.compile(r"^(?:urn:uuid:)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def relation_prefix(value: str) -> str:
    """``"S/O Naresh"`` → ``"S/O "`` (the marker is kept, the name is not)."""
    m = _RELATION_PREFIX.match(value or "")
    return m.group(0) if m else ""


def strip_relation(value: str) -> str:
    """The name part of ``"S/O Naresh Chauhan"``."""
    return (value or "")[len(relation_prefix(value)):]


def is_uuid(value: str) -> bool:
    """FHIR / system UUIDs are not personal data."""
    return bool(_UUID.match(value or ""))


# --------------------------------------------------------------------------- JSON roles

PATIENT_CTX = {"patient", "patients", "subject", "beneficiary", "insured", "claimant", "member",
               "pt", "person", "registrant"}
RELATIVE_CTX = {"guardian", "contact", "relative", "attendant", "nok", "nextofkin", "raisedby",
                "informant", "caller", "father", "husband", "mother", "spouse", "emergencycontact",
                "witness", "relatedperson", "parent", "kin"}
DOCTOR_CTX = {"doctor", "practitioner", "practitionerrole", "performer", "author", "requester",
              "referredby", "consultant", "physician", "recorder", "asserter", "attester",
              "organization", "location", "custodian", "facility", "hospital", "lab", "provider"}
NONPERSON_CTX = {"panels", "panel", "results", "coding", "code", "category", "medication",
                 "medicationcodeableconcept", "valuecodeableconcept", "type", "class", "test",
                 "diagnosis", "rx", "vitals", "wards", "ward", "department", "relationship",
                 "qualification", "section", "export", "exportmeta", "meta", "schema"}
_RESOURCE_CTX = {"Patient": "patient", "RelatedPerson": "relative", "Practitioner": "doctor",
                 "PractitionerRole": "doctor", "Organization": "doctor", "Location": "doctor"}
NAME_KEYS = {"name", "text", "family", "given", "display", "fullname", "first", "last", "local",
             "prefix", "suffix", "patientname", "ptname"}
CLINICAL_KEYS = {"test", "display", "drug", "department", "procedure", "diagnosis", "complaints",
                 "complaint", "category", "unit", "form", "schedule", "status", "frequency",
                 "strength", "duration", "panel", "reporttype", "system", "title", "type"}


@lru_cache(maxsize=65536)
def norm_key(k: str) -> str:
    """Normalised JSON key for context matching."""
    return re.sub(r"[^a-z0-9]", "", (k or "").casefold())


def person_context(path: list[str], resource: str | None) -> str | None:
    """``patient`` / ``relative`` / ``doctor`` / ``nonperson`` from the nearest ancestor."""
    return _person_context(tuple(path), resource)


@lru_cache(maxsize=65536)
def _person_context(path: tuple[str, ...], resource: str | None) -> str | None:
    for k in reversed(path):
        n = norm_key(k)
        if n in RELATIVE_CTX:
            return "relative"
        if n in DOCTOR_CTX:
            return "doctor"
        if n in PATIENT_CTX:
            return "patient"
        if n in NONPERSON_CTX:
            return "nonperson"
    return _RESOURCE_CTX.get(resource or "")


def json_role(key: str, path: list[str], resource: str | None, value: Any) -> str | None:
    """Role of a JSON leaf, using its key and where it sits in the document."""
    n = norm_key(key)
    parents = [norm_key(p) for p in path]
    pctx = person_context(path, resource)
    parent = parents[-1] if parents else ""
    if n in ("id", "fullurl", "reference", "resourcetype", "url", "system", "use", "status",
             "lastupdated", "profile"):
        return C.KEEP
    if n == "value" and parent in ("identifier",) or (n == "value" and "identifier" in parents[-2:]):
        return C.KEEP if is_uuid(str(value)) else C.MRN
    if n == "value" and "telecom" in parents[-2:]:
        return C.EMAIL if "@" in str(value) else C.PHONE
    if "address" in parents[-2:]:
        if n in ("line", "text"):
            return C.ADDRESS
        if n == "city":
            return C.VILLAGE
    if n in ("patientname", "ptname", "patientsname", "fullname") and pctx != "relative":
        return C.PATIENT_NAME
    if n in NAME_KEYS:
        if n == "text" and parent not in ("name",) and "name" not in parents[-2:]:
            return None
        if pctx == "patient":
            return C.PATIENT_NAME
        if pctx == "relative":
            return C.RELATIVE_NAME
        if pctx in ("doctor", "nonperson"):
            return C.DOCTOR if pctx == "doctor" else None
        if n in ("patientname", "ptname"):
            return C.PATIENT_NAME
        if n in ("first", "last", "family", "given", "local"):
            return C.PERSON_NAME
        return None
    role = C.classify_label(key)
    if role in (C.PATIENT_NAME,) and pctx == "relative":
        return C.RELATIVE_NAME
    if role == C.PHONE and pctx == "relative":
        return C.PHONE
    if role == C.DATE and not isinstance(value, str):
        return None
    if role in (C.FACILITY, C.DOCTOR):
        return role
    return role
