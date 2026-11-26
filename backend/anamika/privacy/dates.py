"""Per-patient secret date shifting.

Every date of one patient moves by the same offset, derived from
``HMAC(k_shift, pseudonym)``, so every interval (including length of stay) is exact,
while a global-shift recovery attack (A5) learns nothing about other patients.
"""
from __future__ import annotations

import datetime as dt

from ..safety import Keyring


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
