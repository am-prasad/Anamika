"""Pattern detectors for structured identifiers.

S0 ships the baseline set (phone, 12-digit Aadhaar-like, email, PAN, ``Name:`` label)
plus the Verhoeff checksum used later to boost Aadhaar confidence. S1/S3 extend this
module with ABHA, UHID/MRN label context, PIN, voter ID, Devanagari digits and dose vetoes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass(frozen=True)
class PatternRule:
    """A typed regex rule. ``placeholder`` replaces the match in the output."""

    rule_id: str
    entity: str
    regex: Pattern[str]
    placeholder: str


BASELINE_RULES: tuple[PatternRule, ...] = (
    PatternRule("phone.in10", "PHONE",
                re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"), "[PHONE]"),
    PatternRule("aadhaar.12", "AADHAAR",
                re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)"), "[AADHAAR]"),
    PatternRule("email", "EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    PatternRule("pan", "PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
    PatternRule("label.name", "PATIENT_NAME",
                re.compile(r"(?i)(?<=name:)\s*[^\n,;|]+"), " [NAME]"),
)

# --------------------------------------------------------------------------- Verhoeff

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(digits: str) -> bool:
    """True when ``digits`` (ASCII digits only) passes the Verhoeff checksum."""
    if not digits.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0
