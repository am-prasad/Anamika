"""Keyed, non-reversible pseudonyms: ``PSN-`` + 6 Crockford base32 characters.

``pseudonym = base32(HMAC-SHA256(k_pseudo, cluster_anchor))[:6]``. Without the per-release
secret nobody can recompute or invert it (attack A6), and a new secret yields entirely
new pseudonyms (attack A7). Collisions between different anchors are resolved
deterministically by re-keying with a counter, in sorted-anchor order.
"""
from __future__ import annotations

from typing import Iterable

from ..safety import Keyring

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # no I, L, O, U


def _encode(digest: bytes, length: int = 6) -> str:
    n = int.from_bytes(digest[:8], "big")
    return "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in range(length))


def pseudonym(keys: Keyring, anchor: str, prefix: str = "PSN-", salt: int = 0) -> str:
    """Pseudonym for one cluster anchor (``salt`` is only used to resolve collisions)."""
    msg = anchor if salt == 0 else f"{anchor}\x1f{salt}"
    return prefix + _encode(keys.mac("pseudo", msg))


def assign(keys: Keyring, anchors: Iterable[str], prefix: str = "PSN-") -> dict[str, str]:
    """Map every distinct anchor to a unique pseudonym, deterministically."""
    out: dict[str, str] = {}
    used: set[str] = set()
    for anchor in sorted(set(anchors)):
        salt = 0
        code = pseudonym(keys, anchor, prefix, salt)
        while code in used:
            salt += 1
            code = pseudonym(keys, anchor, prefix, salt)
        used.add(code)
        out[anchor] = code
    return out
