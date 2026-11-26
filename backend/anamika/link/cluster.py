"""Linkage v1: strong-identifier clustering with cannot-link constraints.

Records are joined only through evidence the data itself provides (weak, name-based keys
must also reach a Fellegi–Sunter score threshold over every shared field):

* a shared **strong identifier**: hospital ID (UHID / IPD no.), mobile number, Aadhaar,
  ABHA, e-mail;
* the same **canonical name + date of birth**.

Union-find merges are checked against the whole cluster: two clusters never merge if
they carry different Aadhaar / ABHA numbers, different dates of birth or different
genders. That is how two people with the same name stay apart, and why a merge can never
be transitive through a conflicting record. Records with no strong evidence get no
pseudonym (``null``) — a missed link costs less than a wrong one.

Processing order is fully sorted, so the result is identical on every machine.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

from ..detect.lexicon import GENERIC_NAME_TOKENS

CONFLICT_ATTRS = ("aadhaar", "abha", "dob", "gender")


@dataclass
class Evidence:
    """What one record says about its patient."""

    rid: str                                   # stable record id: "<rel path>\x1f<loc>"
    keys: set[str] = field(default_factory=set)
    attrs: dict[str, set[str]] = field(default_factory=dict)
    name: str | None = None                    # canonical Latin name (exact match with DOB)
    pkey: str | None = None                    # cross-script phonetic name key
    village: str | None = None                 # cross-script village key
    relative: str | None = None                # cross-script key of the relative's name
    pfirst: str | None = None                  # key of the patient's first given name
    rfirst: str | None = None                  # key of the relative's first given name

    def attr(self, name: str, value: str | None) -> None:
        """Record a conflict-checking attribute (e.g. ``dob``)."""
        if value:
            self.attrs.setdefault(name, set()).add(value)


def canonical_name(value: str) -> str | None:
    """Order-independent Latin name key: lower-case tokens, generic parts removed."""
    v = unicodedata.normalize("NFKD", value or "")
    toks = sorted({t for t in re.findall(r"[a-z]+", v.casefold())
                   if len(t) >= 2 and t not in GENERIC_NAME_TOKENS})
    return " ".join(toks) if toks else None


WEAK_KEYS = ("nv:", "nr:", "nf:")
#: first-name + relative-first-name: may only *attach* records to a single existing cluster
UNIQUE_ONLY = "nf:"  # name + village / name + relative: need corroborating age


def _conflict(a: dict[str, set[str]], b: dict[str, set[str]], weak: bool = False) -> bool:
    """Two clusters that cannot be the same person (age is checked for weak keys only)."""
    if any(len(a.get(n, set()) | b.get(n, set())) > 1 for n in CONFLICT_ATTRS):
        return True
    if not weak:
        return False
    ages = [int(x) for x in a.get("age", set()) | b.get("age", set())]
    return bool(ages) and max(ages) - min(ages) > AGE_TOLERANCE


AGE_TOLERANCE = 2

KEY_TYPES = {"mrn": "hospital_id", "ph": "phone", "aa": "aadhaar", "abha": "abha", "em": "email",
             "nd": "name+dob", "ndx": "name+dob (cross-script)", "nv": "name+village+age",
             "nr": "name+relative", "nf": "first-name+relative (fragment)"}


def _reasons(a: dict[str, set[str]], b: dict[str, set[str]]) -> list[str]:
    """Which attributes made two clusters incompatible (names only, never values)."""
    out = [n for n in CONFLICT_ATTRS if len(a.get(n, set()) | b.get(n, set())) > 1]
    ages = [int(x) for x in a.get("age", set()) | b.get("age", set())]
    if ages and max(ages) - min(ages) > AGE_TOLERANCE:
        out.append("age")
    return out  # ages recorded months apart may differ by a year or two


#: Fellegi–Sunter m/u probabilities per field: P(agree | same person), P(agree | different)
FS_MU = {"name": (0.95, 0.01), "village": (0.90, 0.05), "relative": (0.85, 0.02),
         "age": (0.90, 0.10), "gender": (0.99, 0.50), "dob": (0.95, 0.0025)}


def fs_score(a: Evidence, b: Evidence) -> float:
    """Fellegi–Sunter log2 likelihood ratio that two records describe the same person.

    Each field present on both sides contributes ``log2(m/u)`` when it agrees and
    ``log2((1-m)/(1-u))`` when it disagrees; missing fields contribute nothing.
    """
    def term(field_name: str, agree: bool) -> float:
        m, u = FS_MU[field_name]
        return math.log2(m / u) if agree else math.log2((1 - m) / (1 - u))

    score = 0.0
    if a.pkey and b.pkey:
        score += term("name", a.pkey == b.pkey)
    if a.village and b.village:
        score += term("village", a.village == b.village)
    if a.relative and b.relative:
        score += term("relative", a.relative == b.relative)
    ages_a, ages_b = a.attrs.get("age", set()), b.attrs.get("age", set())
    if ages_a and ages_b:
        score += term("age", any(abs(int(x) - int(y)) <= AGE_TOLERANCE for x in ages_a for y in ages_b))
    g_a, g_b = a.attrs.get("gender", set()), b.attrs.get("gender", set())
    if g_a and g_b:
        score += term("gender", bool(g_a & g_b))
    d_a, d_b = a.attrs.get("dob", set()), b.attrs.get("dob", set())
    if d_a and d_b:
        score += term("dob", bool(d_a & d_b))
    return score


class Linker:
    """Collects evidence, clusters, and reports the cluster anchor of every record."""

    def __init__(self, max_cluster: int = 1000, fs_threshold: float = 12.0) -> None:
        self.items: dict[str, Evidence] = {}
        self.max_cluster = max_cluster
        self.fs_threshold = fs_threshold
        self.edges: list[tuple[str, str, str]] = []        # (record, record, key type)
        self.kept_apart: list[tuple[str, str, str, list[str]]] = []  # (rec, rec, key type, reasons)

    def add(self, ev: Evidence) -> None:
        """Register a record's evidence (records without keys stay unlinked)."""
        if ev.name and ev.attrs.get("dob"):
            for dob in ev.attrs["dob"]:
                ev.keys.add(f"nd:{ev.name}|{dob}")
        if ev.pkey:
            for dob in ev.attrs.get("dob", ()):
                ev.keys.add(f"ndx:{ev.pkey}|{dob}")
            if ev.village:
                ev.keys.add(f"nv:{ev.pkey}|{ev.village}")
            if ev.relative:
                ev.keys.add(f"nr:{ev.pkey}|{ev.relative}")
        if ev.pfirst and ev.rfirst:
            ev.keys.add(f"{UNIQUE_ONLY}{ev.pfirst}|{ev.rfirst}")
        self.items[ev.rid] = ev

    def solve(self) -> dict[str, str | None]:
        """Map record id → cluster anchor (``None`` for unlinked records)."""
        parent: dict[str, str] = {}
        attrs: dict[str, dict[str, set[str]]] = {}
        size: dict[str, int] = {}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        rids = sorted(r for r, e in self.items.items() if e.keys)
        for r in rids:
            parent[r] = r
            attrs[r] = {k: set(v) for k, v in self.items[r].attrs.items()}
            size[r] = 1
        by_key: dict[str, list[str]] = {}
        for r in rids:
            for k in self.items[r].keys:
                by_key.setdefault(k, []).append(r)
        unique_only = sorted(k for k in by_key if k.startswith(UNIQUE_ONLY))
        for k in sorted(by_key):
            if k.startswith(UNIQUE_ONLY):
                continue
            members = by_key[k]
            for other in members[1:]:
                a, b = find(members[0]), find(other)
                if a == b:
                    continue
                if _conflict(attrs[a], attrs[b], weak=k.startswith(WEAK_KEYS)):
                    self.kept_apart.append((members[0], other, k.split(":", 1)[0],
                                            _reasons(attrs[a], attrs[b])))
                    continue
                if k.startswith(WEAK_KEYS) and fs_score(self.items[members[0]], self.items[other]) < self.fs_threshold:
                    self.kept_apart.append((members[0], other, k.split(":", 1)[0], ["fs_score"]))
                    continue
                if size[a] + size[b] > self.max_cluster:
                    continue
                if b < a:
                    a, b = b, a
                parent[b] = a
                size[a] += size[b]
                self.edges.append((members[0], other, k.split(":", 1)[0]))
                for n, vals in attrs[b].items():
                    attrs[a].setdefault(n, set()).update(vals)
        # Phase 2: fragment keys attach key-only records to the ONE cluster that already
        # carries the key through stronger evidence; ambiguity (two clusters) links nothing.
        for k in unique_only:
            members = by_key[k]
            anchored = {find(r) for r in members if size[find(r)] > 1}
            if len(anchored) != 1:
                continue
            target = anchored.pop()
            for r in members:
                root = find(r)
                if size[root] == 1 and root != target and not _conflict(attrs[target], attrs[root], weak=True):
                    parent[root] = target
                    size[target] += 1
                    anchor_member = next(m for m in members if find(m) == target and m != r)
                    self.edges.append((anchor_member, r, k.split(":", 1)[0]))
                    for n, vals in attrs[root].items():
                        attrs[target].setdefault(n, set()).update(vals)
        anchors: dict[str, set[str]] = {}
        for r in rids:
            anchors.setdefault(find(r), set()).update(self.items[r].keys)
        # The anchor is the smallest key of the cluster. If two clusters were kept apart by
        # a conflict they can share keys, so a collision is broken by the cluster root.
        first = {root: min(keys) for root, keys in anchors.items()}
        clash = {a for a in first.values() if list(first.values()).count(a) > 1}
        anchor_of_root = {root: (a if a not in clash else f"{a}\x1e{root}") for root, a in first.items()}
        return {r: (anchor_of_root[find(r)] if r in parent else None) for r in sorted(self.items)}
