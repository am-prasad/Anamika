"""Location generalisation: PIN → true 3-digit prefix, village → tehsil (or removed)."""
from __future__ import annotations

import re

from ..detect.patterns import ascii_digits


def pin_prefix(value: str, digits: int = 3) -> str | None:
    """``229073`` → ``229***`` (``digits`` kept); ``None`` if the value is not a PIN."""
    v = ascii_digits(str(value)).strip()
    if not re.fullmatch(r"[1-8]\d{5}", v):
        return None
    if digits >= 6:
        return v
    if digits <= 0:
        return "[PIN]"
    return v[:digits] + "*" * (6 - digits)


def generalise_village(tehsil: str | None) -> str:
    """Replacement for a village value: its tehsil when known, else a placeholder."""
    t = (tehsil or "").strip()
    return t if t else "[VILLAGE]"
