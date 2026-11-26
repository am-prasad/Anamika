"""Rare-value suppression and k-anonymity measurement.

The targeted attack weighs a condition ×8 when at most three profiles share it: a rare
diagnosis or procedure next to a band and a district is a fingerprint. After linkage, we
count **distinct patients** per condition / procedure text. Texts held by fewer than
``kanon.rare_k`` patients are replaced by their ICD-10 chapter (``[ICD chapter: Certain
infectious and parasitic diseases]``), while the ICD **code** itself is kept, so diagnosis
statistics (scored as the ICD distribution) survive. Common conditions are untouched.

``class_sizes`` reports the k distribution of the (age band, gender, district) tuple
across released patients, for the report and the console.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

#: ICD-10 chapters by code range (first letter + two digits)
_CHAPTERS = [
    ("A00", "B99", "Certain infectious and parasitic diseases"), ("C00", "D49", "Neoplasms"),
    ("D50", "D89", "Diseases of the blood and immune mechanism"), ("E00", "E89", "Endocrine, nutritional and metabolic diseases"),
    ("F01", "F99", "Mental and behavioural disorders"), ("G00", "G99", "Diseases of the nervous system"),
    ("H00", "H59", "Diseases of the eye"), ("H60", "H95", "Diseases of the ear"),
    ("I00", "I99", "Diseases of the circulatory system"), ("J00", "J99", "Diseases of the respiratory system"),
    ("K00", "K95", "Diseases of the digestive system"), ("L00", "L99", "Diseases of the skin"),
    ("M00", "M99", "Diseases of the musculoskeletal system"), ("N00", "N99", "Diseases of the genitourinary system"),
    ("O00", "O9A", "Pregnancy and childbirth"), ("P00", "P96", "Perinatal conditions"),
    ("Q00", "Q99", "Congenital malformations"), ("R00", "R99", "Symptoms and abnormal findings"),
    ("S00", "T88", "Injury and poisoning"), ("V00", "Y99", "External causes"), ("Z00", "Z99", "Health status factors"),
]
ICD_RX = re.compile(r"\b([A-TV-Z]\d{2})(?:\.\d{1,4})?\b")
#: "Display text (A01.0)" in free text
DISPLAY_CODE_RX = re.compile(r"([A-Z][A-Za-z ,'’()\-/]{3,90}?)\s*\(([A-TV-Z]\d{2}(?:\.\d{1,4})?)\)")


def chapter(code: str) -> str:
    """ICD-10 chapter title for a code such as ``A01.0`` (``"Unspecified chapter"`` if unknown)."""
    c = (code or "").upper()[:3]
    for lo, hi, name in _CHAPTERS:
        if lo <= c <= hi:
            return name
    return "Unspecified chapter"


def placeholder(code: str | None) -> str:
    """Replacement text for a suppressed rare condition."""
    return f"[ICD chapter: {chapter(code)}]" if code else "[RARE CONDITION]"


class RareValues:
    """Counts distinct patients per condition text and decides which texts are rare."""

    def __init__(self, k: int) -> None:
        self.k = k
        self.holders: dict[str, set[str]] = {}
        self.code: dict[str, str] = {}

    def add(self, text: str, holder: str, code: str | None = None) -> None:
        """Record that ``holder`` (pseudonym or record id) has condition ``text``."""
        t = " ".join((text or "").split())
        if len(t) < 4 or len(t) > 120:
            return
        key = t.casefold()
        self.holders.setdefault(key, set()).add(holder)
        if code and key not in self.code:
            self.code[key] = code

    def rare(self) -> dict[str, str | None]:
        """Rare condition texts (casefolded) → their ICD code if known."""
        if self.k <= 1:
            return {}
        return {t: self.code.get(t) for t, h in self.holders.items() if len(h) < self.k}


def class_sizes(qis: Iterable[tuple]) -> dict[str, int]:
    """k distribution of quasi-identifier tuples: ``{"k=1": n, "k=2": n, "k>=5": n, …}``."""
    counts = Counter(qis)
    dist: Counter[str] = Counter()
    for _, size in counts.items():
        dist["k=1" if size == 1 else "k=2-4" if size < 5 else "k>=5"] += size
    return dict(dist)
