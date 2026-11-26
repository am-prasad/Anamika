"""Truthful age banding for fields and free text: the band always contains the real age.

Only ages in *age forms* are touched (``Age: 48``, ``48 Yrs/M``, ``48 Y / F``, ``48/F``,
``, 48 yrs,``, ``आयु: 48 वर्ष``). Durations such as ``x 12 yrs`` or ``TB 5 yrs back`` and
lab ranges are left alone, so clinical history keeps its meaning.
"""
from __future__ import annotations

import re

from ..detect.patterns import ascii_digits


def age_band(age: int, width: int = 5, top_code: int = 90) -> str:
    """Return ``"45-49"``-style band for ``age``; ages ``>= top_code`` become ``"90+"``."""
    if age < 0:
        raise ValueError("negative age")
    if age >= top_code:
        return f"{top_code}+"
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"


_LABEL = re.compile(r"(?i)(?<![A-Za-z])(?:Age(?:\s*/\s*Sex)?|Umar|आयु|उम्र)\s*[:\-]?\s*(\d{1,3})(?![\d.])")
_SEXED = re.compile(r"(?<![\d.\-])(\d{1,3})\s*(?:Yrs?|Years?|Y|yrs?|years?|वर्ष)?\.?\s*/\s*(?:M|F|Male|Female|पुरुष|महिला)(?![A-Za-z])")
_NARR = re.compile(r"(?:^|,)\s*(\d{1,3})\s*(?:yrs?|years?|Y)\.?\s*(?=,|/|$|\s+(?:old|male|female|M|F)\b)",
                   re.IGNORECASE | re.MULTILINE)
_DEVA = re.compile(r"(?<![\d.])(\d{1,3})\s*वर्ष")
_DURATION_BEFORE = re.compile(r"(?i)(?:\bx|×|since|for|from|past|last|over|h/o\s+\w+|since\s+\w+)\s*$")


def band_text(text: str, width: int = 5, top_code: int = 90) -> tuple[str, int]:
    """Replace the numbers of age expressions with bands; return (text, count)."""
    t = ascii_digits(text)
    spans: dict[int, int] = {}
    for rx in (_LABEL, _SEXED, _NARR, _DEVA):
        for m in rx.finditer(t):
            s, e = m.start(1), m.end(1)
            if _DURATION_BEFORE.search(t[max(0, s - 12):s]):
                continue
            if any(not (e <= a or s >= b) for a, b in spans.items()):
                continue
            spans[s] = e
    if not spans:
        return text, 0
    out, pos = [], 0
    for s in sorted(spans):
        e = spans[s]
        age = int(t[s:e])
        if age > 125:
            continue
        out.append(text[pos:s])
        out.append(age_band(age, width, top_code))
        pos = e
    out.append(text[pos:])
    return "".join(out), len(spans)


def band_value(value: str, width: int = 5, top_code: int = 90) -> str | None:
    """Band a field value (``48``, ``48 वर्ष``, ``48 Yrs``, ``48/F``); ``None`` if not an age."""
    t = ascii_digits(value or "").strip()
    m = re.match(r"^(\d{1,3})(\D*)$", t)
    if not m or int(m.group(1)) > 125:
        return None
    return age_band(int(m.group(1)), width, top_code) + value.strip()[len(m.group(1)):]
