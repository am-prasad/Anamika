"""JSON loading with a depth guard, record-pointer discovery and deterministic dumping.

The depth guard scans brackets (outside strings) *before* parsing, so a 1,500-level
document is quarantined in linear time instead of exhausting the recursion limit.
"""
from __future__ import annotations

import json
from typing import Any

from .sniff import QuarantineError


def max_depth(text: str) -> int:
    """Return the maximum ``[``/``{`` nesting depth of ``text``, ignoring string contents."""
    depth = best = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > best:
                best = depth
        elif ch in "]}":
            depth -= 1
    return best


def load_json(text: str, depth_limit: int) -> Any:
    """Parse JSON text, quarantining over-deep or malformed documents."""
    if max_depth(text) > depth_limit:
        raise QuarantineError("json_too_deep")
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise QuarantineError("malformed_json") from exc


def escape_pointer(token: str) -> str:
    """Escape one RFC 6901 reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def is_fhir_bundle(data: Any) -> bool:
    """True when ``data`` is a FHIR Bundle resource."""
    return isinstance(data, dict) and data.get("resourceType") == "Bundle"


def record_pointers(data: Any) -> list[str]:
    """Locators for the patient records in a JSON document.

    A top-level key whose value is a non-empty list of objects is a record collection
    (``/visits/3``). A FHIR Bundle, a single object or anything else is one ``doc``.
    """
    if is_fhir_bundle(data) or not isinstance(data, dict):
        return ["doc"]
    pointers = [
        f"/{escape_pointer(k)}/{i}"
        for k, v in data.items()
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)
        for i in range(len(v))
    ]
    return pointers or ["doc"]


def dump_json(data: Any) -> str:
    """Serialise ``data`` as UTF-8-friendly, indented JSON preserving key order."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
