"""Per-patient secret date shifting, format-preserving.

Every date of one patient moves by the same offset, derived from ``HMAC(k_shift, key)``,
so every interval (including length of stay) is exact, while a global-shift recovery
attack (A5) learns nothing about other patients. Dates are found in free text and
fields in all common Indian formats and re-rendered exactly in their original format
(separators, zero padding, 2/4-digit years, month names, ISO time and zone).
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from typing import Callable

from ..detect.patterns import ascii_digits
from ..safety import Keyring

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]
_MON_RX = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

ISO_RX = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})"
                    r"(T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?(?![\d])")
NUM4_RX = re.compile(r"(?<![\d/.-])(\d{1,2})([/.-])(\d{1,2})\2(\d{4})(?![\d/-]|\.\d)")
NUM2_RX = re.compile(r"(?<![\d/.-])(\d{1,2})/(\d{1,2})/(\d{2})(?![\d/])")
NAME_RX = re.compile(r"(?<![\dA-Za-z])(\d{1,2})(\s+|-)(" + _MON_RX + r")\.?(?:(,?\s+|-)(\d{4}|\d{2}))?(?![A-Za-z\d])",
                     re.IGNORECASE)


def shift_days(keys: Keyring, scope_key: str, min_days: int = 30, max_days: int = 365,
               multiple_of_7: bool = False) -> int:
    """Deterministic offset in ``[-max, -min] ∪ [min, max]`` days for ``scope_key``."""
    if not 0 < min_days <= max_days:
        raise ValueError("invalid shift range")
    digest = keys.mac("shift", scope_key)
    span = max_days - min_days + 1
    magnitude = min_days + int.from_bytes(digest[:4], "big") % span
    if multiple_of_7:
        magnitude = max(7, (magnitude // 7) * 7)
    sign = -1 if digest[4] & 1 else 1
    return sign * magnitude


def shift_date(value: dt.date, offset_days: int) -> dt.date:
    """Shift a date (or datetime) by ``offset_days``."""
    return value + dt.timedelta(days=offset_days)


@dataclass(frozen=True)
class DateHit:
    """A date found in text: span, parsed value and a renderer for the shifted value."""

    start: int
    end: int
    value: dt.date
    render: Callable[[dt.date], str]


def _pad(template: str, n: int) -> str:
    """Render ``n`` with the width of ``template`` (``05`` → two digits, ``5`` → as is)."""
    return f"{n:02d}" if len(template) == 2 else str(n)


def _valid(y: int, m: int, d: int) -> dt.date | None:
    if not (1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= calendar.monthrange(y, m)[1]):
        return None
    return dt.date(y, m, d)


def infer_order(text: str) -> str | None:
    """``dmy`` / ``mdy`` if unambiguous numeric dates in ``text`` reveal the convention."""
    dmy = mdy = 0
    for m in NUM4_RX.finditer(ascii_digits(text)):
        a, b = int(m.group(1)), int(m.group(3))
        if a > 12 >= b:
            dmy += 1
        elif b > 12 >= a:
            mdy += 1
    if mdy > dmy:
        return "mdy"
    if dmy > mdy:
        return "dmy"
    return None


def find_dates(text: str, order: str = "dmy", default_year: int = 2026) -> list[DateHit]:
    """Every calendar-valid date in ``text`` (ISO, d/m/Y, m/d/Y, d/m/yy, d Mon Y, d Month)."""
    t = ascii_digits(text)
    hits: list[DateHit] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    for m in ISO_RX.finditer(t):
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            tail = m.group(4) or ""
            hits.append(DateHit(m.start(), m.end(), d, lambda x, tail=tail: x.isoformat() + tail))
            taken.append((m.start(), m.end()))
    for m in NUM4_RX.finditer(t):
        if not free(m.start(), m.end()):
            continue
        a, sep, b, y = m.group(1), m.group(2), m.group(3), m.group(4)
        ia, ib = int(a), int(b)
        o = order
        if ia > 12 >= ib:
            o = "dmy"
        elif ib > 12 >= ia:
            o = "mdy"
        d = _valid(int(y), ib, ia) if o == "dmy" else _valid(int(y), ia, ib)
        if not d:
            continue

        def render(x: dt.date, a=a, b=b, sep=sep, o=o) -> str:
            first, second = (x.day, x.month) if o == "dmy" else (x.month, x.day)
            return f"{_pad(a, first)}{sep}{_pad(b, second)}{sep}{x.year}"

        hits.append(DateHit(m.start(), m.end(), d, render))
        taken.append((m.start(), m.end()))
    for m in NUM2_RX.finditer(t):
        if not free(m.start(), m.end()):
            continue
        a, b, y = m.group(1), m.group(2), int(m.group(3))
        ia, ib = int(a), int(b)
        o = "mdy" if (order == "mdy" and ib <= 12 or ib > 12 >= ia) else "dmy"
        d = _valid(2000 + y, ib, ia) if o == "dmy" else _valid(2000 + y, ia, ib)
        if not d:
            continue

        def render2(x: dt.date, a=a, b=b, o=o) -> str:
            first, second = (x.day, x.month) if o == "dmy" else (x.month, x.day)
            return f"{_pad(a, first)}/{_pad(b, second)}/{x.year % 100:02d}"

        hits.append(DateHit(m.start(), m.end(), d, render2))
        taken.append((m.start(), m.end()))
    for m in NAME_RX.finditer(t):
        if not free(m.start(), m.end()):
            continue
        day, sep1, mon, sep2, yr = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        mi = next(i for i, full in enumerate(_MONTHS, 1) if full.startswith(mon.casefold()[:3]))
        if yr is None and len(mon) < 4:
            continue  # "5 Mar" without a year is too ambiguous; full month names only
        year = int(yr) if yr and len(yr) == 4 else (2000 + int(yr) if yr else default_year)
        d = _valid(year, mi, int(day))
        if not d:
            continue
        abbreviated = len(mon) <= 4 and mon.casefold() not in ("june", "july")

        def render3(x: dt.date, day=day, sep1=sep1, mon=mon, sep2=sep2, yr=yr,
                    abbreviated=abbreviated) -> str:
            name = _MONTHS[x.month - 1]
            name = name[:len(mon)] if abbreviated else name
            name = name.upper() if mon.isupper() else (name.capitalize() if mon[0].isupper() else name)
            out = f"{_pad(day, x.day)}{sep1}{name}"
            if yr is not None:
                out += sep2 + (str(x.year) if len(yr) == 4 else f"{x.year % 100:02d}")
            return out

        hits.append(DateHit(m.start(), m.end(), d, render3))
        taken.append((m.start(), m.end()))
    return sorted(hits, key=lambda h: h.start)


def parse_date(value: str, order: str = "dmy") -> dt.date | None:
    """Parse a field that is exactly one date (returns ``None`` otherwise)."""
    v = (value or "").strip()
    hits = find_dates(v, order)
    if len(hits) == 1 and hits[0].start == 0 and hits[0].end == len(v):
        return hits[0].value
    return None


def shift_text(text: str, offset: int, order: str = "dmy") -> tuple[str, int]:
    """Shift every date in ``text`` by ``offset`` days; return (text, number shifted)."""
    hits = find_dates(text, order)
    if not hits:
        return text, 0
    out, pos = [], 0
    for h in hits:
        out.append(text[pos:h.start])
        out.append(h.render(shift_date(h.value, offset)))
        pos = h.end
    out.append(text[pos:])
    return "".join(out), len(hits)
