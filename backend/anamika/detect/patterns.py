"""Pattern detectors for structured identifiers (applied to digit-normalised text).

Every rule is anchored so that clinical numbers never match: a phone needs 10 digits
starting 6–9 bounded by non-digits, an Aadhaar exactly 12, ABHA 14; doses (``650 mg``),
frequencies (``1-0-1``), vitals (``117/82``) and lab values are far too short. Matching
runs on text whose Devanagari digits were mapped to ASCII (same length, same offsets).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

_DEVA_DIGITS = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}


def ascii_digits(text: str) -> str:
    """Map Devanagari digits to ASCII; offsets are unchanged (1 char → 1 char)."""
    return text.translate(_DEVA_DIGITS)


@dataclass(frozen=True)
class PatternRule:
    """A typed regex rule. ``group`` selects the identifier inside the match."""

    rule_id: str
    entity: str
    regex: Pattern[str]
    group: int = 0


_NB = r"(?<![0-9A-Za-z])"   # not preceded by an alphanumeric
_NA = r"(?![0-9A-Za-z])"    # not followed by an alphanumeric

RULES: tuple[PatternRule, ...] = (
    PatternRule("email", "EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    PatternRule("abha.address", "ABHA_ADDRESS",
                re.compile(r"(?i)" + _NB + r"[a-z0-9._]{3,}@(?:abdm|sbx|ndhm)" + _NA)),
    PatternRule("abha.number", "ABHA_NUMBER",
                re.compile(_NB + r"\d{2}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}" + _NA)),
    PatternRule("aadhaar.masked", "AADHAAR_MASKED",
                re.compile(r"(?i)" + _NB + r"[x*]{4}[\s-]?[x*]{4}[\s-]?\d{4}" + _NA)),
    PatternRule("aadhaar.spaced", "AADHAAR", re.compile(_NB + r"\d{4}[\s-]\d{4}[\s-]\d{4}" + _NA)),
    PatternRule("aadhaar.plain", "AADHAAR", re.compile(r"(?<![0-9A-Za-z-])\d{12}(?![0-9A-Za-z-])")),
    PatternRule("phone.in", "PHONE", re.compile(
        r"(?<![0-9A-Za-z])(?:(?:\+|00)?91[\s.-]?|0)?[6-9](?:[\s.-]?\d){9}(?![0-9A-Za-z])")),
    PatternRule("abha.plain", "ABHA_NUMBER", re.compile(_NB + r"\d{14}" + _NA)),
    PatternRule("pan", "PAN", re.compile(_NB + r"[A-Z]{3}[ABCFGHLJPTK][A-Z]\d{4}[A-Z]" + _NA)),
    PatternRule("pin.label", "PIN", re.compile(
        r"(?i)(?:PIN(?:\s*Code)?|Pincode|Zip|पिन(?:\s*कोड)?)\s*(?:No\.?)?\s*[:\-]?\s*([1-8]\d{5})" + _NA), 1),
)

PHONE_RX = RULES[6].regex
EMAIL_RX = RULES[0].regex

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


def digits_only(s: str) -> str:
    """ASCII digits of ``s`` (after Devanagari digit mapping)."""
    return re.sub(r"\D", "", ascii_digits(s))


def phone_key(s: str) -> str | None:
    """Canonical 10-digit Indian mobile number, or ``None``."""
    d = digits_only(s)
    if len(d) >= 10 and d[-10] in "6789":
        return d[-10:]
    return None
