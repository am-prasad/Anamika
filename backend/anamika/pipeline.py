"""The two-pass sanitisation pipeline.

Pass A (understand)
    1. observe every string → which words are ordinary vocabulary of this dataset;
    2. classify CSV columns / JSON keys and feed the run-time lexicon (names, IDs, places,
       protected doctors / tehsils / districts, clinical vocabulary);
    3. harvest names / IDs / villages from unambiguous text labels;
    4. compile the lexicon, extract per-record identity evidence, link records.

Pass B (rewrite)
    Rewrite every file in its own format with pseudonyms, typed placeholders, per-patient
    date shifts, age bands, PIN prefixes and village → tehsil; clean JSON keys, CSV
    headers, export metadata, base64 attachments and file names.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from . import policy as pol
from .detect import columns as C
from .detect.engine import Detector, Span
from .detect.lexicon import ADMIN_PLACE_MARKERS
from .detect.patterns import ascii_digits, digits_only, phone_key
from .detect.runtime import RuntimeLexicon
from .ingest.csv_io import write_table
from .ingest.json_io import dump_json, escape_pointer, is_fhir_bundle, record_pointers
from .link.cluster import Evidence, Linker, canonical_name
from .link.pseudonym import CROCKFORD, assign
from .privacy import ages, dates, location
from .rewrite import fields as F
from .safety import Keyring

_B64 = re.compile(r"^[A-Za-z0-9+/]{24,}={0,2}$")
_ADMIN = re.compile(rf"^\s*{ADMIN_PLACE_MARKERS}", re.IGNORECASE)
_WARD = re.compile(r"^\s*(?:Ward|Bed|Room)\s*\d+\s*$", re.IGNORECASE)
_RELATIVE_LINE = re.compile(r"(?i)(?:attendant|guardian|S/O|D/O|W/O|C/O|father|husband|mother|"
                            r"informant|relative|पिता|पति|पत्नी|पुत्र|visitor)")
HARVEST_NAME_RULES = {"label.patient", "label.pt", "label.relative", "relation.marker",
                      "relation.deva", "title.pre", "title.pre.deva", "report.of", "verb.by",
                      "whatsapp.sender", "honorific.post", "honorific.post.deva",
                      "hinglish.possessive"}
PATIENT_RULES = {"label.patient", "label.pt", "report.of"}


@dataclass
class Item:
    """A parsed input file."""

    rel: str
    sha: str
    fmt: str          # csv | tsv | json | text
    payload: Any
    locs: list[str]
    order: str = "dmy"
    roles: list[str] = field(default_factory=list)   # CSV column roles
    out_rel: str = ""


def rid(rel: str, loc: str) -> str:
    """Stable record id."""
    return f"{rel}\x1f{loc}"


class Pipeline:
    """Holds run-wide state between Pass A and Pass B."""

    def __init__(self, keys: Keyring, policy: Mapping[str, Any]) -> None:
        self.keys, self.policy = keys, policy
        self.lex = RuntimeLexicon()
        self.det = Detector(self.lex)
        self.linker = Linker(int(pol.get(policy, "linkage.max_cluster_size", 1000)))
        self.psn: dict[str, str | None] = {}
        self.id_psn: dict[str, str] = {}
        self.entities: Counter[str] = Counter()
        self.generalized: set[str] = set()
        self.band = int(pol.get(policy, "ages.band_years", 5))
        self.top = int(pol.get(policy, "ages.top_code", 90))
        self.pin_digits = int(pol.get(policy, "location.pin_digits", 3))
        self.smin = int(pol.get(policy, "dates.shift_min_days", 30))
        self.smax = int(pol.get(policy, "dates.shift_max_days", 365))
        self.s7 = bool(pol.get(policy, "dates.shift_multiple_of_7", False))
        self.prefix = str(pol.get(policy, "output.pseudonym_prefix", "PSN-"))

    # ================================================================ Pass A
    def observe(self, items: list[Item]) -> None:
        """Step 1: lower-case vocabulary of the whole dataset."""
        for it in items:
            for s in _strings(it):
                self.lex.observe_text(s)

    def learn(self, items: list[Item]) -> None:
        """Steps 2–4: classify, feed the lexicon, harvest labels, compile, link."""
        for it in items:
            if it.fmt in ("csv", "tsv"):
                self._learn_csv(it)
            elif it.fmt == "json":
                self._walk(it.payload, [], None, lambda *a: self._learn_leaf(*a), None)
        for it in items:
            for s in _text_strings(it):
                self._harvest(s)
        self.lex.compile()
        for it in items:
            self._evidence(it)
        anchors = self.linker.solve()
        mapping = assign(self.keys, [a for a in anchors.values() if a], self.prefix)
        self.psn = {r: (mapping[a] if a else None) for r, a in anchors.items()}
        for r, ev in self.linker.items.items():
            p = self.psn.get(r)
            if p:
                for k in ev.keys:
                    if k.startswith("mrn:"):
                        self.id_psn.setdefault(k[4:], p)

    def _learn_csv(self, it: Item) -> None:
        header, rows = it.payload
        cols = list(zip(*rows)) if rows else [[] for _ in header]
        it.roles = []
        for j, h in enumerate(header):
            values = [str(v) for v in (cols[j] if j < len(cols) else [])]
            role = C.classify_column(h, values)
            it.roles.append(role)
            hint = C.date_order_hint(h)
            if hint and role in (C.DOB, C.DATE):
                it.order = hint
            for v in values:
                self._feed(role, v)
            if role == C.TEXT:
                counts = Counter(v for v in values if v)
                for v, n in counts.items():
                    if n >= 3 and len(v) <= 60:
                        self.lex.add_safe_phrase(v)

    def _feed(self, role: str | None, v: Any) -> None:
        v = "" if v is None else str(v)
        if not v.strip():
            return
        if role in C.NAME_ROLES:
            self.lex.add_name(F.strip_relation(v))
        elif role in (C.MRN, C.INSURANCE):
            self.lex.add_id(v)
        elif role in (C.VILLAGE, C.LOCALITY, C.HOUSE):
            self.lex.add_place(v)
        elif role == C.ADDRESS:
            for seg in v.split(","):
                seg = seg.strip()
                if not seg or _ADMIN.match(seg) or _WARD.match(seg):
                    continue
                if F.relation_prefix(seg):
                    self.lex.add_name(F.strip_relation(seg))
                elif len(seg) >= 6 and not re.fullmatch(r"[\d\s-]+", seg):
                    self.lex.add_place(seg)
        elif role in (C.DOCTOR, C.TEHSIL, C.DISTRICT, C.STATE, C.FACILITY):
            self.lex.add_protected(v)

    def _learn_leaf(self, key: str, path: list[str], resource: str | None, value: Any) -> Any:
        role = F.json_role(key, path, resource, value)
        if role and role not in (C.KEEP, C.TEXT, C.DATE):
            self._feed(role, value)
        if (role in (None, C.KEEP) and F.norm_key(key) in F.CLINICAL_KEYS and isinstance(value, str)
                and len(value) <= 80 and F.person_context(path, resource) == "nonperson"):
            self.lex.add_safe_phrase(value)
        return value

    def _harvest(self, text: str) -> None:
        t = ascii_digits(text)
        for s in self.det.context_names(t):
            if s.rule in HARVEST_NAME_RULES:
                self.lex.add_name(t[s.start:s.end])
        for s in self.det.labelled_places_ids(t):
            val = t[s.start:s.end]
            if s.etype in ("MRN", "INSURANCE_ID"):
                self.lex.add_id(val)
            elif s.etype == "VILLAGE" or (s.etype == "ADDRESS" and len(val) >= 6 and not _WARD.match(val)):
                if not F.relation_prefix(val):
                    self.lex.add_place(val)
        for a, b in self.det.protected(t):
            seg = t[a:b]
            if not seg.startswith("<"):
                self.lex.add_protected(re.sub(r"(?i)^(?:dr|doctor)\.?\s*", "", seg))

    # ---------------------------------------------------------------- evidence
    def _evidence(self, it: Item) -> None:
        if it.fmt in ("csv", "tsv"):
            header, rows = it.payload
            for i, row in enumerate(rows):
                ev = Evidence(rid(it.rel, f"row:{i}"))
                fields = {}
                for j, v in enumerate(row):
                    role = it.roles[j] if j < len(it.roles) else C.TEXT
                    self._ev_field(ev, role, v, it.order, fields)
                self._ev_name(ev, fields)
                self.linker.add(self._guard(ev))
        elif it.fmt == "json":
            data = it.payload
            fhir = is_fhir_bundle(data)
            ev = Evidence(rid(it.rel, "doc"))
            fields: dict[str, list[str]] = {}
            if fhir:
                root: Any = _fhir_patient(data)
            elif isinstance(data, dict):
                coll = _collections(it)
                root = {k: v for k, v in data.items() if k not in coll}
            else:
                root = data if it.locs == ["doc"] else {}
            self._walk(root, [], "Patient" if fhir else None,
                       lambda k, p, r, v: self._ev_leaf(ev, k, p, r, v, it.order, fields), None)
            self._ev_name(ev, fields)
            self.linker.add(self._guard(ev))
            for loc in it.locs:
                if loc == "doc":
                    continue
                node = _resolve(data, loc)
                ev = Evidence(rid(it.rel, loc))
                fields = {}
                key = loc.split("/")[1].replace("~1", "/").replace("~0", "~")
                self._walk(node, [key], None,
                           lambda k, p, r, v: self._ev_leaf(ev, k, p, r, v, it.order, fields), None)
                self._ev_name(ev, fields)
                self.linker.add(self._guard(ev))
        else:
            ev = Evidence(rid(it.rel, "doc"))
            self._ev_text(ev, it.payload, it.order)
            self.linker.add(self._guard(ev))

    def _ev_field(self, ev: Evidence, role: str | None, v: Any, order: str, fields: dict) -> None:
        s = "" if v is None else str(v).strip()
        if not s:
            return
        if role == C.MRN:
            ev.keys.add("mrn:" + ascii_digits(s).upper())
        elif role == C.PHONE:
            k = phone_key(s)
            if k:
                ev.keys.add("ph:" + k)
        elif role == C.AADHAAR:
            d = digits_only(s)
            if len(d) == 12:
                ev.keys.add("aa:" + d)
                ev.attr("aadhaar", d)
        elif role == C.ABHA:
            d = digits_only(s)
            if len(d) == 14:
                ev.keys.add("abha:" + d)
                ev.attr("abha", d)
        elif role == C.EMAIL and "@" in s:
            ev.keys.add("em:" + s.casefold())
        elif role == C.DOB:
            d = dates.parse_date(s, order)
            if d:
                ev.attr("dob", d.isoformat())
        elif role == C.GENDER:
            g = _gender(s)
            if g:
                ev.attr("gender", g)
        elif role in (C.PATIENT_NAME, C.FIRST_NAME, C.LAST_NAME):
            fields.setdefault(role, []).append(s)

    def _ev_name(self, ev: Evidence, fields: dict) -> None:
        parts = fields.get(C.PATIENT_NAME) or (fields.get(C.FIRST_NAME, []) + fields.get(C.LAST_NAME, []))
        if parts:
            ev.name = canonical_name(" ".join(parts))

    def _ev_leaf(self, ev: Evidence, key: str, path: list[str], resource: str | None, value: Any,
                 order: str, fields: dict) -> Any:
        role = F.json_role(key, path, resource, value)
        pctx = F.person_context(path, resource)
        if pctx == "relative" and role in (C.PHONE, C.EMAIL, C.RELATIVE_NAME):
            return value
        if role == C.TEXT or role is None:
            return value
        self._ev_field(ev, role, value, order, fields)
        return value

    def _ev_text(self, ev: Evidence, text: str, order: str) -> None:
        t = ascii_digits(text)
        for s in self.det.detect(t):
            val = t[s.start:s.end]
            line = t[t.rfind("\n", 0, s.start) + 1: (t.find("\n", s.end) + 1 or len(t) + 1) - 1]
            if s.etype == "MRN" and s.rule in ("label.id", "lex.id"):
                ev.keys.add("mrn:" + val.upper())
            elif s.etype == "PHONE" and not _RELATIVE_LINE.search(line):
                k = phone_key(val)
                if k:
                    ev.keys.add("ph:" + k)
            elif s.etype == "AADHAAR":
                ev.keys.add("aa:" + digits_only(val))
                ev.attr("aadhaar", digits_only(val))
            elif s.etype == "ABHA_NUMBER":
                ev.keys.add("abha:" + digits_only(val))
                ev.attr("abha", digits_only(val))
            elif s.etype == "PATIENT_NAME" and s.rule in PATIENT_RULES and not ev.name:
                ev.name = canonical_name(val)
        m = re.search(r"(?im)^\s*(?:DOB|Date\s+of\s+Birth|जन्म\s*तिथि)\s*[:\-]\s*(\S+)", t)
        if m:
            d = dates.parse_date(m.group(1).rstrip(".,"), order)
            if d:
                ev.attr("dob", d.isoformat())
        g = re.search(r"(?i)\b\d{1,3}\s*(?:Yrs?|Y)?\s*/\s*(M|F|Male|Female)\b|(पुरुष|महिला)", t)
        if g:
            ev.attr("gender", _gender(g.group(1) or g.group(2)))

    @staticmethod
    def _guard(ev: Evidence) -> Evidence:
        """A record naming several patients (an index, a ward sheet) links nobody."""
        per_type = Counter(k.split(":", 1)[0] for k in ev.keys)
        if per_type["mrn"] > 3 or per_type["ph"] > 2 or per_type["aa"] > 1 or per_type["abha"] > 1:
            ev.keys.clear()
            ev.attrs.clear()
        return ev

    # ================================================================ Pass B
    def offset(self, psn: str | None, record: str) -> int:
        """Secret date offset: per patient when linked, per record otherwise."""
        scope = ("patient:" + psn) if psn else ("record:" + record)
        return dates.shift_days(self.keys, scope, self.smin, self.smax, self.s7)

    def rewrite(self, it: Item) -> str:
        """Pass B for one file: sanitised text in the original format."""
        if it.fmt in ("csv", "tsv"):
            return self._rewrite_csv(it)
        if it.fmt == "json":
            return self._rewrite_json(it)
        r = rid(it.rel, "doc")
        psn = self.psn.get(r)
        return self.text(it.payload, psn, self.offset(psn, r), it.order, r)

    # ---------------------------------------------------------------- text
    def text(self, text: str, psn: str | None, offset: int, order: str, record: str,
             mode: str = "text") -> str:
        """Sanitise free text: PII spans, dates, ages and embedded base64 payloads."""
        if not text:
            return text
        spans = self.det.detect(text, mode)
        repl: list[tuple[int, int, str]] = []
        for s in spans:
            repl.append((s.start, s.end, self._placeholder(s, text, psn)))
            self.entities[s.etype if s.etype != "PERSON_NAME" else "PATIENT_NAME"] += 1
        taken = [(a, b) for a, b, _ in repl]
        changed = bool(repl)
        if mode == "text":
            for h in dates.find_dates(text, order):
                if all(h.end <= a or h.start >= b for a, b in taken):
                    repl.append((h.start, h.end, h.render(dates.shift_date(h.value, offset))))
                    taken.append((h.start, h.end))
                    changed = True
        out = _apply(text, repl)
        if mode == "text":
            out, n = ages.band_text(out, self.band, self.top)
            changed |= bool(n)
        if changed:
            self.generalized.add(record)
        return out

    def _placeholder(self, s: Span, text: str, psn: str | None) -> str:
        if s.etype == "PATIENT_NAME" and s.rule in PATIENT_RULES and psn:
            return psn
        if s.etype == "MRN":
            mapped = self.id_psn.get(ascii_digits(text[s.start:s.end]).upper())
            return mapped or psn or "[MRN]"
        if s.etype == "PIN":
            return location.pin_prefix(text[s.start:s.end], self.pin_digits) or "[PIN]"
        return {"PATIENT_NAME": "[NAME]", "PERSON_NAME": "[NAME]", "RELATIVE_NAME": "[RELATIVE]",
                "PHONE": "[PHONE]", "EMAIL": "[EMAIL]", "AADHAAR": "[AADHAAR]",
                "AADHAAR_MASKED": "[AADHAAR]", "ABHA_NUMBER": "[ABHA]", "ABHA_ADDRESS": "[ABHA]",
                "PAN": "[PAN]", "INSURANCE_ID": "[INSURANCE_ID]", "ADDRESS": "[ADDRESS]",
                "VILLAGE": "[VILLAGE]"}.get(s.etype, "[REDACTED]")

    # ---------------------------------------------------------------- fields
    def field(self, role: str | None, value: Any, psn: str | None, offset: int, order: str,
              record: str, row: dict[str, str] | None = None) -> Any:
        """Transform one structured value according to its role."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return value
        if isinstance(value, bool):
            return value
        s = str(value)
        ent = F.ENTITY_OF_ROLE.get(role or "")
        if role in (C.PATIENT_NAME, C.FIRST_NAME, C.LOCAL_NAME):
            self.entities["PATIENT_NAME"] += 1
            return psn or "[NAME]"
        if role in (C.RELATIVE_NAME, C.GUARDIAN):
            self.entities["RELATIVE_NAME"] += 1
            return F.relation_prefix(s) + "[RELATIVE]"
        if role == C.MRN:
            self.entities["MRN"] += 1
            return self.id_psn.get(ascii_digits(s).strip().upper()) or psn or "[MRN]"
        if role in F.PLACEHOLDER:
            self.entities[ent or "OTHER"] += 1
            return F.PLACEHOLDER[role]
        if role == C.VILLAGE:
            self.entities["VILLAGE"] += 1
            self.generalized.add(record)
            return location.generalise_village((row or {}).get(C.TEHSIL))
        if role == C.PIN:
            p = location.pin_prefix(s, self.pin_digits)
            if p:
                self.entities["PIN"] += 1
                self.generalized.add(record)
                return p
            return self.text(s, psn, offset, order, record)
        if role == C.ADDRESS:
            self.entities["ADDRESS"] += 1
            return self._address(s, psn, offset, order, record)
        if role in (C.DOB, C.DATE):
            out, n = dates.shift_text(s, offset, order)
            if n:
                self.generalized.add(record)
                if role == C.DOB:
                    self.entities["DOB"] += 1
                return out
            return self.text(s, psn, offset, order, record)
        if role in (C.AGE, C.AGE_SEX):
            b = ages.band_value(s, self.band, self.top)
            if b is None:
                b, n = ages.band_text(s, self.band, self.top)
                b = b if n else s
            self.generalized.add(record)
            return b
        if role in (C.GENDER, C.TEHSIL, C.DISTRICT, C.STATE, C.RELATION, C.DOCTOR, C.FACILITY, C.KEEP):
            return value
        if isinstance(value, (int, float)):
            return value
        return self.text(s, psn, offset, order, record)

    def _address(self, s: str, psn: str | None, offset: int, order: str, record: str) -> str:
        keep = [seg.strip() for seg in s.split(",") if _ADMIN.match(seg.strip())]
        pin = re.search(r"([1-8]\d{5})\s*$", ascii_digits(s))
        out = "[ADDRESS]" + ("".join(", " + k for k in keep))
        if pin:
            out = re.sub(r"\s*[-–]?\s*[1-8]\d{5}\s*$", "", out)
            out += " - " + (location.pin_prefix(pin.group(1), self.pin_digits) or "[PIN]")
        self.generalized.add(record)
        return out

    # ---------------------------------------------------------------- CSV
    def _rewrite_csv(self, it: Item) -> str:
        header, rows = it.payload
        new_header = [self._name_channel(h, "header") for h in header]
        out_rows = []
        for i, row in enumerate(rows):
            r = rid(it.rel, f"row:{i}")
            psn = self.psn.get(r)
            off = self.offset(psn, r)
            ctx = {it.roles[j]: v for j, v in enumerate(row) if j < len(it.roles)}
            out_rows.append([self.field(it.roles[j] if j < len(it.roles) else C.TEXT, v, psn, off,
                                        it.order, r, ctx) for j, v in enumerate(row)])
        return write_table(new_header, out_rows, "\t" if it.fmt == "tsv" else ",")

    def _name_channel(self, s: str, channel: str) -> str:
        """Clean a header / key / path segment with lexicon + patterns only."""
        spans = [self._grow_name(s, sp) if sp.etype in ("PERSON_NAME", "PATIENT_NAME", "RELATIVE_NAME")
                 else sp for sp in self.det.detect(s, "name")]
        if not spans:
            return s
        repl = []
        for sp in spans:
            val = s[sp.start:sp.end]
            mapped = self.id_psn.get(ascii_digits(val).upper()) if sp.etype == "MRN" else None
            repl.append((sp.start, sp.end, mapped or self._token(val, channel)))
            self.entities[sp.etype if sp.etype != "PERSON_NAME" else "PATIENT_NAME"] += 1
        return _apply(s, repl)

    _NEIGHBOUR_L = re.compile(r"([A-Z][a-z]{2,})[_\s-]$")
    _NEIGHBOUR_R = re.compile(r"^[_\s-]([A-Z][a-z]{2,})(?![a-z])")

    def _grow_name(self, s: str, sp: Span) -> Span:
        """In names / keys / headers, swallow adjacent Title-case name parts (``Farida_Bano``)."""
        start, end = sp.start, sp.end
        while True:
            m = self._NEIGHBOUR_L.search(s[:start])
            if not m or self.lex.is_common_word(m.group(1)):
                break
            start = m.start(1)
        while True:
            m = self._NEIGHBOUR_R.match(s[end:])
            if not m or self.lex.is_common_word(m.group(1)):
                break
            end += m.end(1)
        return Span(start, end, sp.etype, sp.rule)

    def _token(self, value: str, channel: str) -> str:
        d = self.keys.mac("file", channel + "\x1f" + value)
        n = int.from_bytes(d[:5], "big")
        return "X" + "".join(CROCKFORD[(n >> (5 * i)) & 31] for i in range(6))

    # ---------------------------------------------------------------- JSON
    def _rewrite_json(self, it: Item) -> str:
        data = it.payload
        doc = rid(it.rel, "doc")
        doc_psn = self.psn.get(doc)
        doc_off = self.offset(doc_psn, doc)
        coll = _collections(it)
        if not coll:
            return dump_json(self._json_node(data, [], None, doc_psn, doc_off, it.order, doc))
        out: dict[str, Any] = {}
        for k, v in data.items():
            nk = self._name_channel(k, "key")
            if k in coll:
                items = []
                for i, x in enumerate(v):
                    r = rid(it.rel, f"/{escape_pointer(k)}/{i}")
                    psn = self.psn.get(r) or doc_psn
                    if psn and not self.psn.get(r):
                        self.psn[r] = psn
                    items.append(self._json_node(x, [k], None, psn, self.offset(psn, r), it.order, r))
                out[_unique(out, nk)] = items
            else:
                out[_unique(out, nk)] = self._json_node(v, [k], None, doc_psn, doc_off, it.order, doc, key=k)
        return dump_json(out)

    def _json_node(self, node: Any, path: list[str], resource: str | None, psn: str | None,
                   off: int, order: str, record: str, key: str = "") -> Any:
        if isinstance(node, dict):
            res = node.get("resourceType") if isinstance(node.get("resourceType"), str) else resource
            out: dict[str, Any] = {}
            for k, v in node.items():
                nk = k if k in _FHIR_KEYS else self._name_channel(k, "key")
                out[_unique(out, nk)] = self._json_node(v, path + [k], res, psn, off, order, record, key=k)
            return out
        if isinstance(node, list):
            return [self._json_node(v, path, resource, psn, off, order, record, key=key) for v in node]
        if node is None or isinstance(node, bool):
            return node
        parent_path = path[:-1] if path and path[-1] == key else path
        role = F.json_role(key, parent_path, resource, node)
        if isinstance(node, str) and role in (None, C.TEXT) and _B64.match(node) and len(node) % 4 == 0:
            return self._b64(node, psn, off, order, record)
        if isinstance(node, str) and F.norm_key(key) == "div":
            return self.text(node, psn, off, order, record)
        if role is None and isinstance(node, str):
            d = dates.parse_date(node, order)
            if d:
                out, _ = dates.shift_text(node, off, order)
                return out
        if role is None and isinstance(node, (int, float)):
            return node
        return self.field(role or C.TEXT, node, psn, off, order, record)

    def _b64(self, value: str, psn: str | None, off: int, order: str, record: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return self.text(value, psn, off, order, record)
        try:
            inner = raw.decode("utf-8")
            printable = sum(c.isprintable() or c in "\r\n\t" for c in inner) / max(len(inner), 1)
        except UnicodeDecodeError:
            printable = 0.0
        if printable < 0.9:
            self.entities["ATTACHMENT"] += 1
            return base64.b64encode(b"[ATTACHMENT REMOVED]").decode()
        clean = self.text(inner, psn, off, order, record)
        return base64.b64encode(clean.encode("utf-8")).decode()

    # ---------------------------------------------------------------- walkers
    def _walk(self, node: Any, path: list[str], resource: str | None,
              leaf: Callable[[str, list[str], str | None, Any], Any], _unused: Any) -> None:
        stack = [(node, path, resource, path[-1] if path else "")]
        while stack:
            n, p, res, key = stack.pop()
            if isinstance(n, dict):
                r = n.get("resourceType") if isinstance(n.get("resourceType"), str) else res
                for k, v in n.items():
                    stack.append((v, p + [k], r, k))
            elif isinstance(n, list):
                for v in n:
                    stack.append((v, p, res, key))
            else:
                parent = p[:-1] if p and p[-1] == key else p
                leaf(key, parent, res, n)

    # ---------------------------------------------------------------- file names
    def output_path(self, rel: str) -> str:
        """Input relative path → output path with PII removed from every segment."""
        parts = PurePosixPath(rel).parts
        out = []
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                stem, dot, ext = part.rpartition(".")
                if not dot:
                    stem, ext = part, ""
                clean = self._name_channel(stem, "filename")
                out.append(clean + (("." + ext) if dot else ""))
            else:
                out.append(self._name_channel(part, "filename"))
        return "/".join(out)


# --------------------------------------------------------------------------- helpers

_FHIR_KEYS = {"resourceType", "id", "meta", "text", "div", "status", "entry", "resource", "fullUrl"}


def _collections(it: Item) -> set[str]:
    """Top-level keys whose lists are record collections (from the item's locators)."""
    return {loc.split("/")[1].replace("~1", "/").replace("~0", "~") for loc in it.locs if loc != "doc"}


def _apply(text: str, repl: list[tuple[int, int, str]]) -> str:
    if not repl:
        return text
    out, pos = [], 0
    for a, b, r in sorted(repl):
        if a < pos:
            continue
        out.append(text[pos:a])
        out.append(r)
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _unique(d: dict, key: str) -> str:
    if key not in d:
        return key
    i = 2
    while f"{key}_{i}" in d:
        i += 1
    return f"{key}_{i}"


def _gender(v: str | None) -> str | None:
    s = (v or "").strip().casefold()
    if s in ("m", "male", "पुरुष", "man", "boy"):
        return "m"
    if s in ("f", "female", "महिला", "woman", "girl", "स्त्री"):
        return "f"
    return None


def _resolve(data: Any, pointer: str) -> Any:
    node = data
    for tok in pointer.split("/")[1:]:
        tok = tok.replace("~1", "/").replace("~0", "~")
        node = node[int(tok)] if isinstance(node, list) else node[tok]
    return node


def _fhir_patient(bundle: dict) -> Any:
    for e in bundle.get("entry") or []:
        res = (e or {}).get("resource") or {}
        if res.get("resourceType") == "Patient":
            return res
    return {}


def _strings(it: Item):  # type: ignore[no-untyped-def]
    if it.fmt in ("csv", "tsv"):
        header, rows = it.payload
        yield from header
        for row in rows:
            yield from row
    elif it.fmt == "json":
        stack = [it.payload]
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
            elif isinstance(n, str):
                yield n
    else:
        yield it.payload


def _text_strings(it: Item):  # type: ignore[no-untyped-def]
    """Free-text strings worth harvesting labels from."""
    if it.fmt == "text":
        yield it.payload
    elif it.fmt in ("csv", "tsv"):
        header, rows = it.payload
        for row in rows:
            for j, v in enumerate(row):
                if j < len(it.roles) and it.roles[j] in (C.TEXT, C.ADDRESS) and v:
                    yield v
    else:
        for s in _strings(it):
            if _B64.match(s) and len(s) % 4 == 0:
                try:
                    yield base64.b64decode(s).decode("utf-8", "ignore")
                except (binascii.Error, ValueError):
                    pass
            elif len(s) > 12 and " " in s:
                yield s
