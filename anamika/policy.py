"""Policy loader: reads ``config/policy.yaml`` into a typed, read-only view.

All privacy knobs (shift ranges, band widths, k, generalisation targets) come from the
policy file. ``ANAMIKA_POLICY`` may point to an alternative file (used by the demo
console presets); otherwise the repository default is used.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = REPO_ROOT / "config" / "policy.yaml"


def _freeze(obj: Any) -> Any:
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


def load_policy(path: Path | None = None) -> Mapping[str, Any]:
    """Load the policy YAML (``ANAMIKA_POLICY`` env var overrides the default path)."""
    target = path or Path(os.environ.get("ANAMIKA_POLICY", DEFAULT_POLICY))
    with open(target, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("policy must be a mapping")
    return _freeze(data)


def get(policy: Mapping[str, Any], dotted: str, default: Any = None) -> Any:
    """Fetch ``a.b.c`` from a nested policy mapping, returning ``default`` if absent."""
    node: Any = policy
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node
