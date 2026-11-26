"""Truthful age banding: the band always contains the real age."""
from __future__ import annotations


def age_band(age: int, width: int = 5, top_code: int = 90) -> str:
    """Return ``"45-49"``-style band for ``age``; ages ``>= top_code`` become ``"90+"``."""
    if age < 0:
        raise ValueError("negative age")
    if age >= top_code:
        return f"{top_code}+"
    lo = (age // width) * width
    return f"{lo}-{lo + width - 1}"
