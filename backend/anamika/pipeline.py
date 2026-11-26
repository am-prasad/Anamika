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
from .detect.lexicon import ADMIN_PLACE_MARKERS, DISTRICT_MARKERS, TEHSIL_MARKERS
from .detect.patterns import ascii_digits, digits_only, phone_key
from .detect.runtime import RuntimeLexicon
from .ingest.csv_io import write_table
from .ingest.json_io import dump_json, escape_pointer, is_fhir_bundle, record_pointers
from .link.cluster import Evidence, Linker, canonical_name
from .link.pseudonym import CROCKFORD, assign
from .translit.keys import first_key, name_key, place_key
from .privacy import ages, dates, kanon, location
from .rewrite import fields as F
from .safety import Keyring

_B64 = re.compile(r"^[A-Za-z0-9+/]{24,}={0,2}$")
_ADMIN = re.compile(rf"^\s*{ADMIN_PLACE_MARKERS}", re.IGNORECASE)
_DISTRICT = re.compile(rf"^\s*{DISTRICT_MARKERS}", re.IGNORECASE)
_WARD = re.compile(r"^\s*(?:Ward|Bed|Room)\s*\d+\s*$", re.IGNORECASE)
_RELATIVE_LINE = re.compile(r"(?i)(?:attendant|guardian|S/O|D/O|W/O|C/O|father|husband|mother|"
                            r"informant|relative|पिता|पति|पत्नी|पुत्र|visitor)")
HARVEST_NAME_RULES = {"label.patient", "label.pt", "label.relative", "relation.marker",
                      "relation.deva", "title.pre", "title.pre.deva", "report.of", "verb.by",
                      "whatsapp.sender", "honorific.post", "honorific.post.deva", "relation.subject",
                      "hinglish.possessive", "kinship", "kinship.deva", "patient.word.deva"}
PATIENT_RULES = {"label.patient", "label.pt", "report.of", "relation.subject"}


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
        self.linker = Linker(int(pol.get(policy, "linkage.max_cluster_size", 5000)),
                             float(pol.get(policy, "linkage.fs_threshold", 12.0)))
        self.psn: dict[str, str | None] = {}
        self.id_psn: dict[str, str] = {}
        self.entities: Counter[str] = Counter()
        self.generalized: set[str] = set()
        self.suppressed: set[str] = set()
        self.band = int(pol.get(policy, "ages.band_years", 5))
        self.top = int(pol.get(policy, "ages.top_code", 90))
        self.pin_digits = int(pol.get(policy, "location.pin_digits", 3))
        self.smin = int(pol.get(policy, "dates.shift_min_days", 30))
        self.smax = int(pol.get(policy, "dates.shift_max_days", 365))
        self.s7 = bool(pol.get(policy, "dates.shift_multiple_of_7", False))
        self.prefix = str(pol.get(policy, "output.pseudonym_prefix", "PSN-"))
        self.level = str(pol.get(policy, "location.level", "tehsil"))
        self.rare_k = int(pol.get(policy, "kanon.rare_k", 0))
        self.rare_rx: re.Pattern[str] | None = None
        self.rare_code: dict[str, str | None] = {}
        self.lex.keep_tehsil = self.level == "tehsil"
        self.lex.keep_district = self.level != "state"
        self.dob_policy = str(pol.get(policy, "ages.dob_policy", "shift"))

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
                for node, header, rows_key in _iter_tables(it.payload):
                    cols = list(zip(*node[rows_key]))
                    for j, h in enumerate(header):
                        vals = [str(x) for x in cols[j] if x is not None]
                        role = C.classify_column(h, vals)
                        if role == C.TEXT:
                            role = C.profile_people_places(vals, self.lex.is_common_word) or C.TEXT
                        for v in vals:
                            self._feed(role, v)
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
        if self.rare_k > 1:
            self._learn_rare(items)

    def _learn_csv(self, it: Item) -> None:
        header, rows = it.payload
        cols = list(zip(*rows)) if rows else [[] for _ in header]
        it.roles = []
        for j, h in enumerate(header):
            values = [str(v) for v in (cols[j] if j < len(cols) else [])]
            role = C.classify_column(h, values)
            if role == C.TEXT:
                role = C.profile_people_places(values, self.lex.is_common_word) or C.TEXT
                if role == C.PERSON_NAME and C.PATIENT_NAME not in it.roles:
                    role = C.PATIENT_NAME
            it.roles.append(role)
            hint = C.date_order_hint(h)
            if hint and role in (C.DOB, C.DATE):
                it.order = hint
            for v in values:
                self._feed(role, v)
            if role == C.CLINICAL:
                for v in set(values):
                    self.lex.add_safe_phrase(v)
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
        elif role == C.DISTRICT:
            self.lex.add_admin(v, "district")
        elif role == C.TEHSIL:
            self.lex.add_admin(v, "tehsil")
        elif role in (C.DOCTOR, C.STATE, C.FACILITY):
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
            if seg.startswith("<"):
                continue
            m = re.match(rf"(?i)\s*({TEHSIL_MARKERS}|{DISTRICT_MARKERS})\s*\.?\s*[:\-]?\s*(.+)", seg)
            if m:
                kind = "tehsil" if re.match(rf"(?i){TEHSIL_MARKERS}", m.group(1)) else "district"
                self.lex.add_admin(m.group(2), kind)
            else:
                self.lex.add_protected(re.sub(r"(?i)^(?:dr|doctor)\.?\s*", "", seg))

    # ---------------------------------------------------------------- rare values
    def _learn_rare(self, items: list[Item]) -> None:
        """Count distinct patients per condition / procedure text; compile the rare ones."""
        rv = kanon.RareValues(self.rare_k)
        for it in items:
            if it.fmt in ("csv", "tsv"):
                header, rows = it.payload
                for i, row in enumerate(rows):
                    r = rid(it.rel, f"row:{i}")
                    holder = self.psn.get(r) or r
                    for j, v in enumerate(row):
                        if j < len(it.roles) and it.roles[j] == C.CLINICAL and v and \
                                _CONDITION_HEADER.search(header[j]) and not re.fullmatch(r"[\d.\s/-]+", v):
                            rv.add(v, holder)
                        for m in kanon.DISPLAY_CODE_RX.finditer(v or ""):
                            rv.add(m.group(1), holder, m.group(2))
            elif it.fmt == "json":
                holder = self.psn.get(rid(it.rel, "doc")) or rid(it.rel, "doc")
                stack: list[tuple[Any, str]] = [(it.payload, holder)]
                ptrs = {loc for loc in it.locs if loc != "doc"}
                while stack:
                    node, h = stack.pop()
                    if isinstance(node, dict):
                        code = node.get("code")
                        disp = node.get("display") or node.get("text")
                        if isinstance(code, str) and kanon.ICD_RX.fullmatch(code) and isinstance(disp, str):
                            rv.add(disp, h, code)
                        for k, v in node.items():
                            if isinstance(v, str) and C.classify_label(k) == C.CLINICAL and F.norm_key(k) in (
                                    "procedure", "diagnosis", "dx", "condition"):
                                rv.add(v, h)
                            elif isinstance(v, str):
                                for m in kanon.DISPLAY_CODE_RX.finditer(v):
                                    rv.add(m.group(1), h, m.group(2))
                            else:
                                stack.append((v, h))
                    elif isinstance(node, list):
                        stack.extend((v, h) for v in node)
                for loc in ptrs:
                    r = rid(it.rel, loc)
                    if self.psn.get(r):
                        node = _resolve(it.payload, loc)
                        for txt in _strings(Item(it.rel, it.sha, "json", node, ["doc"])):
                            for m in kanon.DISPLAY_CODE_RX.finditer(txt):
                                rv.add(m.group(1), self.psn[r], m.group(2))
            else:
                r = rid(it.rel, "doc")
                holder = self.psn.get(r) or r
                for m in kanon.DISPLAY_CODE_RX.finditer(it.payload):
                    rv.add(m.group(1), holder, m.group(2))
        rare = rv.rare()
        self.rare_code = rare
        if rare:
            alts = sorted(rare, key=len, reverse=True)
            self.rare_rx = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(a) for a in alts) + r")(?![\w])",
                                      re.IGNORECASE)

    def suppress_rare(self, text: str, record: str) -> str:
        """Replace rare condition / procedure texts by their ICD chapter (codes are kept)."""
        if self.rare_rx is None or not text:
            return text

        def sub(m: re.Match[str]) -> str:
            self.entities["RARE_CONDITION"] += 1
            self.suppressed.add(record)
            return kanon.placeholder(self.rare_code.get(" ".join(m.group(0).split()).casefold()))

        return self.rare_rx.sub(sub, text)

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
        elif role in (C.PATIENT_NAME, C.FIRST_NAME, C.LAST_NAME, C.LOCAL_NAME):
            fields.setdefault(role, []).append(s)
        elif role in (C.RELATIVE_NAME, C.GUARDIAN):
            fields.setdefault("relative", []).append(F.strip_relation(s))
        elif role == C.VILLAGE:
            fields.setdefault("village", []).append(s)
        elif role in (C.AGE, C.AGE_SEX):
            m = re.match(r"\s*(\d{1,3})", ascii_digits(s))
            if m and int(m.group(1)) <= 125:
                ev.attr("age", m.group(1))

    def _ev_name(self, ev: Evidence, fields: dict) -> None:
        parts = fields.get(C.PATIENT_NAME) or (fields.get(C.FIRST_NAME, []) + fields.get(C.LAST_NAME, []))
        if parts:
            ev.name = canonical_name(" ".join(parts))
            ev.pkey = name_key(" ".join(parts))
            ev.pfirst = first_key(" ".join(parts))
        elif fields.get(C.LOCAL_NAME):
            ev.pkey = name_key(" ".join(fields[C.LOCAL_NAME]))
        if fields.get("village"):
            ev.village = place_key(fields["village"][0])
        if fields.get("relative"):
            ev.relative = name_key(fields["relative"][0])
            ev.rfirst = first_key(fields["relative"][0])

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
            if s.etype == "MRN" and s.rule in ("label.id", "lex.id", "label.field"):
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
        # name / village / relative evidence straight from the context detectors (merged
        # spans may carry a lexicon rule id instead of the label that found them)
        for s in sorted(self.det.context_names(t), key=lambda x: x.start):
            val = t[s.start:s.end]
            if s.etype == "PATIENT_NAME" and s.rule in PATIENT_RULES and not ev.pkey:
                ev.name = canonical_name(val)
                ev.pkey = name_key(val)
                ev.pfirst = first_key(val)
            elif s.etype == "RELATIVE_NAME" and s.rule in ("relation.marker", "relation.deva") \
                    and not ev.relative:
                ev.relative = name_key(val)
                ev.rfirst = first_key(val)
        for s in self.det.labelled_places_ids(t):
            if s.etype == "VILLAGE" and s.rule == "label.village" and not ev.village:
                ev.village = place_key(t[s.start:s.end])
        m = re.search(r"(?im)^\s*(?:DOB|Date\s+of\s+Birth|जन्म\s*तिथि)\s*[:\-]\s*(\S+)", t)
        if m:
            d = dates.parse_date(m.group(1).rstrip(".,"), order)
            if d:
                ev.attr("dob", d.isoformat())
        a = re.search(r"(?i)(?<![A-Za-z])(?:Age(?:\s*/\s*Sex)?|आयु|उम्र)\s*[:\-]?\s*(\d{1,3})(?!\d)"
                      r"|(\d{1,3})\s*(?:Yrs?|Y|वर्ष)\.?\s*/\s*(?:M|F|पुरुष|महिला)", t)
        if a:
            ev.attr("age", a.group(1) or a.group(2))
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
        if mode == "text" and self.dob_policy in ("year", "remove"):
            for m in _DOB_LABEL.finditer(text):
                for h in dates.find_dates(text[m.end():m.end() + 30], order)[:1]:
                    a, b = m.end() + h.start, m.end() + h.end
                    if h.start == 0 and all(b <= x or a >= y for x, y in taken):
                        repl.append((a, b, str(h.value.year) if self.dob_policy == "year" else "[DOB]"))
                        taken.append((a, b))
                        changed = True
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
            out = self.suppress_rare(out, record)
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
                "PAN": "[PAN]", "VOTER_ID": "[VOTER_ID]", "INSURANCE_ID": "[INSURANCE_ID]", "ADDRESS": "[ADDRESS]",
                "VILLAGE": "[VILLAGE]", "TEHSIL": "[TEHSIL]"}.get(s.etype, "[REDACTED]")

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
            norm = " ".join(s.split()).casefold()
            admin = {"tehsil": self.lex.districts | self.lex.tehsils, "district": self.lex.districts}.get(self.level, set())
            if norm in admin:
                return value  # already a tehsil / district: generalised, research value
            self.entities["VILLAGE"] += 1
            self.generalized.add(record)
            up = {"tehsil": C.TEHSIL, "district": C.DISTRICT}.get(self.level, C.STATE)
            return location.generalise_village((row or {}).get(up))
        if role == C.TEHSIL and self.level in ("district", "state"):
            self.generalized.add(record)
            up = C.DISTRICT if self.level == "district" else C.STATE
            return (row or {}).get(up) or "[TEHSIL]"
        if role == C.DISTRICT and self.level == "state":
            self.generalized.add(record)
            return (row or {}).get(C.STATE) or "[DISTRICT]"
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
        if role == C.DOB and self.dob_policy in ("year", "remove"):
            d = dates.parse_date(s, order)
            self.entities["DOB"] += 1
            self.generalized.add(record)
            if self.dob_policy == "year" and d:
                return str(d.year)
            return "[DOB]"
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
        if role == C.CLINICAL:
            return self.text(s, psn, offset, order, record) if isinstance(value, str) else value
        if isinstance(value, (int, float)):
            return value
        return self.text(s, psn, offset, order, record)

    def _address(self, s: str, psn: str | None, offset: int, order: str, record: str) -> str:
        admin = {"tehsil": _ADMIN, "district": _DISTRICT}.get(self.level)
        keep = [seg.strip() for seg in s.split(",") if admin and admin.match(seg.strip())]
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
        if isinstance(node, dict) and table_shape(node):
            header, rows_key = table_shape(node)  # type: ignore[misc]
            cols = list(zip(*node[rows_key]))
            roles = []
            for j, h in enumerate(header):
                vals = [str(x) for x in cols[j] if x is not None]
                role = C.classify_column(h, vals)
                if role == C.TEXT:
                    role = C.profile_people_places(vals, self.lex.is_common_word) or C.TEXT
                roles.append(role)
            out = {}
            for k, v in node.items():
                if k == rows_key:
                    out[k] = [[self.field(roles[j], x, psn, off, order, record) for j, x in enumerate(row)]
                              for row in v]
                else:
                    out[k] = self._json_node(v, path + [k], resource, psn, off, order, record, key=k)
            return out
        if isinstance(node, dict):
            res = node.get("resourceType") if isinstance(node.get("resourceType"), str) else resource
            out: dict[str, Any] = {}
            for k, v in node.items():
                if k == "birthDate" and res and self.dob_policy == "remove":
                    self.entities["DOB"] += 1
                    continue  # optional in FHIR R4: dropping it keeps the resource valid
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

    # ---------------------------------------------------------------- identity graph
    def linkage_graph(self, outputs: dict[str, str]) -> dict[str, Any]:
        """Value-free identity graph: exported records, the evidence *types* that linked them,
        and pairs kept apart by conflicting attributes (e.g. same name, different DOB)."""
        from .link.cluster import KEY_TYPES

        ids: dict[str, int] = {}
        nodes = []
        for r in sorted(self.linker.items):
            rel, loc = r.split("\x1f", 1)
            if rel not in outputs:
                continue
            ids[r] = len(nodes)
            ev = self.linker.items[r]
            nodes.append({"id": ids[r], "file": outputs[rel], "loc": loc, "patient": self.psn.get(r),
                          "evidence": sorted({KEY_TYPES.get(k.split(":", 1)[0], k.split(":", 1)[0])
                                              for k in ev.keys})})
        edges = [{"source": ids[a], "target": ids[b], "type": KEY_TYPES.get(t, t)}
                 for a, b, t in self.linker.edges if a in ids and b in ids]
        apart = [{"a": ids[a], "b": ids[b], "patient_a": self.psn.get(a), "patient_b": self.psn.get(b),
                  "shared": KEY_TYPES.get(t, t), "conflict": reasons}
                 for a, b, t, reasons in self.linker.kept_apart if a in ids and b in ids]
        clusters = Counter(n["patient"] for n in nodes if n["patient"])
        return {"nodes": nodes, "edges": edges, "kept_apart": apart,
                "summary": {"records": len(nodes), "linked": sum(1 for n in nodes if n["patient"]),
                            "patients": len(clusters), "largest_cluster": max(clusters.values(), default=0),
                            "kept_apart_pairs": len(apart)}}

    # ---------------------------------------------------------------- explainability
    def explain(self, it: Item) -> dict[str, Any]:
        """Value-free explanation of what was found in a file (for ``--debug-spans``).

        Text: character spans with entity type and the rule that fired, plus date and
        age hits. CSV: the role of every column. JSON: the role of every classified leaf
        path. Never contains the values themselves.
        """
        info: dict[str, Any] = {"format": it.fmt, "records": len(it.locs)}
        if it.fmt == "text":
            t = it.payload
            info["spans"] = [{"start": s.start, "end": s.end, "type": s.etype, "rule": s.rule}
                             for s in self.det.detect(t)]
            info["kept"] = [{"start": a, "end": b, "type": "PROTECTED"} for a, b in self.det.protected(t)
                            if not t[a:b].startswith("<")]
            info["dates"] = [{"start": h.start, "end": h.end} for h in dates.find_dates(t, it.order)]
        elif it.fmt in ("csv", "tsv"):
            info["columns"] = [{"index": j, "role": r} for j, r in enumerate(it.roles)]
        else:
            paths: Counter[tuple[str, str]] = Counter()

            def leaf(k: str, p: list[str], r: str | None, v: Any) -> Any:
                role = F.json_role(k, p, r, v)
                if role:
                    paths[("/" + "/".join(F.norm_key(x) for x in p + [k]), role)] += 1
                return v

            self._walk(it.payload, [], None, leaf, None)
            info["fields"] = [{"path": pth, "role": role, "count": n} for (pth, role), n in sorted(paths.items())]
        return info

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
                clean = _DEVA_RUN.sub(lambda m: m.group(0) if m.group(0) in _DEVA_DOC_WORDS
                                      else self._token(m.group(0), "filename"),
                                      self._name_channel(stem, "filename"))
                out.append(clean + (("." + ext) if dot else ""))
            else:
                out.append(self._name_channel(part, "filename"))
        return "/".join(out)


# --------------------------------------------------------------------------- helpers

_CONDITION_HEADER = re.compile(r"(?i)diagnos|\bdx\b|condition|disease|procedure|निदान|बीमारी|रोग")
_DOB_LABEL = re.compile(r"(?i)(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Birth\s*(?:Date|Dt)|जन्म\s*तिथि|Janm\s*Tithi)\s*[:\-]?\s*")
_DEVA_RUN = re.compile(r"[\u0900-\u0963\u0970-\u097F]+")
#: Devanagari words that describe documents; any other Devanagari word in a file name is
#: treated as a possible name (file names carry no clinical value worth the risk).
_DEVA_DOC_WORDS = frozenset("पर्चा रिपोर्ट डिस्चार्ज सारांश जांच नोट्स पंजीकरण बिल दवा".split())
_FHIR_KEYS = {"resourceType", "id", "meta", "text", "div", "status", "entry", "resource", "fullUrl"}


def table_shape(node: Any) -> tuple[list[str], str] | None:
    """``{"columns": [...names], "rows": [[...], ...]}`` → (header, rows key), else ``None``."""
    if not isinstance(node, dict):
        return None
    header = next((v for v in node.values() if isinstance(v, list) and v
                   and all(isinstance(x, str) for x in v)), None)
    if header is None:
        return None
    for k, v in node.items():
        if isinstance(v, list) and v and all(isinstance(r, list) and len(r) == len(header) for r in v):
            return header, k
    return None


def _iter_tables(data: Any):  # type: ignore[no-untyped-def]
    stack = [data]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            t = table_shape(n)
            if t:
                yield n, t[0], t[1]
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)


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
