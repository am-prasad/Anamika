"""Free-text rewriting: replace detected spans with typed placeholders.

Counts every replacement per entity type so ``report.json`` reports true numbers.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from ..detect.patterns import BASELINE_RULES, PatternRule


def clean_text(text: str, counts: Counter[str],
               rules: Iterable[PatternRule] = BASELINE_RULES) -> str:
    """Apply ``rules`` in order to ``text``; add per-entity hit counts to ``counts``."""
    for rule in rules:
        text, n = rule.regex.subn(rule.placeholder, text)
        if n:
            counts[rule.entity] += n
    return text


def clean_value(value: Any, counts: Counter[str]) -> Any:
    """Recursively clean a JSON value. Keys are cleaned too; non-strings keep their type."""
    if isinstance(value, str):
        return clean_text(value, counts)
    if isinstance(value, list):
        return [clean_value(v, counts) for v in value]
    if isinstance(value, dict):
        return {clean_text(k, counts): clean_value(v, counts) for k, v in value.items()}
    return value
