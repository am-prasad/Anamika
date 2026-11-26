"""Text detection engine: typed PII spans from patterns, context and the run-time lexicon.

Layers, in order of trust:

1. **Patterns** (:mod:`.patterns`): phones, Aadhaar, ABHA, PAN, e-mail, labelled PINs.
2. **Labels and context**: ``Name:``/``नाम:`` → patient; ``S/o``, ``W/o``, ``C/O <name>``,
   ``पुत्र``, ``Attendant:`` → relative; ``UHID:``/``पंजीकरण सं.`` → identifier;
   ``Address:``/``पता:`` → address (tehsil and district clauses are kept);
   ``Mohd.``/``Smt.``/``श्री`` and Hinglish ``ji``/``sahab``/``जी`` honorifics → names.
3. **Run-time lexicon**: names, IDs and places learned from this dataset's structured data.
4. **Capitalised-phrase heuristic**: 2–3 Title-case tokens that are not vocabulary of this
   dataset (never seen in lower case, not clinical) — catches names no list contains.

**Protected spans** veto name and place spans: ``Dr. <name>`` (doctors stay), facility
names (``… Hospital``, ``… Pathology``), and ``Tehsil``/``Distt.`` administrative places.
``C/O`` followed by a complaint (``C/O fever``) is not a relative; ``K/C/O`` and ``H/o``
are medical history.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import lexicon as L
from .patterns import RULES, ascii_digits
from .runtime import RuntimeLexicon

DEVA = r"ऀ-ॣ॰-ॿ"
_LAT_TOK = re.compile(r"(?:[A-Z][A-Za-z'’-]*\.?|[A-Z]\.)")
_DEVA_TOK = re.compile(rf"[{DEVA}]+\.?")


@dataclass(frozen=True)
class Span:
    """A detected entity. ``etype`` follows the scorer's types; ``rule`` names the detector."""

    start: int
    end: int
    etype: str
    rule: str

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end


NAME_TYPES = {"PATIENT_NAME", "RELATIVE_NAME", "PERSON_NAME"}
PLACE_TYPES = {"ADDRESS", "VILLAGE", "TEHSIL"}
_PRIORITY = {"EMAIL": 9, "ABHA_ADDRESS": 9, "ABHA_NUMBER": 9, "AADHAAR": 9, "AADHAAR_MASKED": 9,
             "PHONE": 8, "PAN": 8, "VOTER_ID": 8, "TEHSIL": 3, "MRN": 7, "INSURANCE_ID": 7, "PATIENT_NAME": 6,
             "RELATIVE_NAME": 5, "PERSON_NAME": 4, "ADDRESS": 3, "VILLAGE": 3, "PIN": 2}

# --------------------------------------------------------------------------- name scanning


def scan_name(text: str, pos: int, max_tokens: int = 4, allow_lower: bool = False,
              lex: RuntimeLexicon | None = None) -> tuple[int, int] | None:
    """Span of a person name starting at ``pos`` (after a label), or ``None``.

    Accepts Title/UPPER Latin tokens, initials and Devanagari words, separated by single
    spaces; stops at digits, punctuation, double spaces, line ends and stop-words.
    """
    i = pos
    n = len(text)
    while i < n and text[i] in " \t:-–.":
        i += 1
    start = i
    end = None
    count = 0
    while i < n and count < max_tokens:
        m = _LAT_TOK.match(text, i) or _DEVA_TOK.match(text, i)
        if not m and allow_lower:
            m = re.compile(r"[a-z][a-z'’-]+").match(text, i)
        if not m:
            break
        tok = m.group(0).rstrip(".")
        low = tok.casefold()
        if low in L.NAME_STOPWORDS or (count == 0 and low in L.GENERIC_NAME_TOKENS and False):
            break
        if lex is not None and count > 0 and lex.is_common_word(tok) and low not in lex.name_latin:
            break
        if low in L.CLINICAL_WORDS and (lex is None or low not in lex.name_latin):
            break
        count += 1
        end = m.end()
        i = m.end()
        if m.group(0).endswith(".") and len(tok) > 2 and low not in L.GENERIC_NAME_TOKENS:
            end -= 1  # a full word followed by "." ends the sentence, not an initial
            break
        if i < n and text[i] == " " and (i + 1 >= n or text[i + 1] != " "):
            i += 1
            continue
        break
    if end is None:
        return None
    if text[end - 1] == "." and len(text[start:end].split()[-1]) > 2:
        end -= 1
    return (start, end)


# --------------------------------------------------------------------------- compiled rules

def _rx(p: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(p, flags)


_LABEL_END = r"\s*(?:\([^)\n]{0,20}\))?\s*[:\-–]\s*"
PATIENT_LABEL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.PATIENT_NAME_LABELS}){_LABEL_END}", re.IGNORECASE)
PT_DOT_RX = _rx(r"(?<![A-Za-z])Pt\.\s+(?=[A-Z])")
RELATIVE_LABEL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.RELATIVE_LABELS}){_LABEL_END}", re.IGNORECASE)
RELATION_RX = _rx(rf"(?<![A-Za-z/])(?:{L.RELATION_MARKERS})\.?\s*[:\-]?\s*", re.IGNORECASE)
RELATION_DEVA_RX = _rx(rf"(?<![{DEVA}])(?:{L.RELATION_MARKERS_DEVA})\s*[:\-]?\s+")
SUBJECT_OF_RELATION_RX = _rx(rf"(?m)^\s*((?:[A-Z][a-z'’]+\s){{0,2}}[A-Z][a-z'’]+)\s*,\s*(?i:{L.RELATION_MARKERS})")
PRE_TITLE_RX = _rx(rf"(?<![A-Za-z])(?:{L.PRE_TITLES})\.?\s+(?=[A-Z])")
PRE_TITLE_DEVA_RX = _rx(rf"(?<![{DEVA}])(?:{L.PRE_TITLES_DEVA})\s+(?=[{DEVA}])")
POST_HON_RX = _rx(rf"((?:[A-Z][a-z'’]+\s+){{0,2}}[A-Z][a-z'’]+)\s+{L.POST_HONORIFICS}(?![A-Za-z])")
POST_HON_DEVA_RX = _rx(rf"((?:[{DEVA}]+\s+){{0,1}}[{DEVA}]+)\s+{L.POST_HONORIFICS_DEVA}(?![{DEVA}])")
HINGLISH_POSS_RX = _rx(rf"((?:[A-Z][a-z'’]+\s+){{0,2}}[A-Z][a-z'’]+)\s+{L.HINGLISH_PARTICLES}\s+(?=[A-Za-z])")
KIN_RX = _rx(rf"(?<![A-Za-z]){L.KINSHIP}\s+(?!of\b)(?=[A-Z])", re.IGNORECASE)
KIN_DEVA_RX = _rx(rf"(?<![{DEVA}]){L.KINSHIP_DEVA}\s+(?=[{DEVA}])")
PATIENT_WORD_DEVA_RX = _rx(rf"(?<![{DEVA}]){L.PATIENT_WORDS_DEVA}\s+(?=[{DEVA}])")
PERSON_VERB_RX = _rx(rf"(?<![A-Za-z]){L.PERSON_VERBS}\s+", re.IGNORECASE)
REPORT_OF_RX = _rx(r"(?<![A-Za-z])Report\s+(?:of|for)\s+(?=[A-Z])", re.IGNORECASE)
WA_SENDER_RX = _rx(r"(?m)^\[[^\]\n]{5,30}\]\s*(?=[^:\n]{2,40}:)")
ID_LABEL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.ID_LABELS})\s*[:\-.#]?\s*([A-Za-z0-9][A-Za-z0-9/\-]{{3,30}})",
                  re.IGNORECASE)
INS_LABEL_RX = _rx(rf"(?<![A-Za-z])(?:{L.INSURANCE_LABELS})\s*[:\-.#]?\s*([A-Za-z0-9][A-Za-z0-9/\-]{{3,30}})",
                   re.IGNORECASE)
ADDRESS_LABEL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.ADDRESS_LABELS})(?:\s*\([^)\n]{{0,20}}\))?\s*[:\-]\s*",
                       re.IGNORECASE)
VILLAGE_LABEL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.VILLAGE_LABELS})\s*[:\-.]?\s+", re.IGNORECASE)
DISTRICT_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.DISTRICT_MARKERS})\s*\.?\s*[:\-]?\s*", re.IGNORECASE)
TEHSIL_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.TEHSIL_MARKERS})\s*\.?\s*[:\-]?\s*", re.IGNORECASE)
ADMIN_RX = _rx(rf"(?<![\w{DEVA}])(?:{L.ADMIN_PLACE_MARKERS})\s*\.?\s*[:\-]?\s*", re.IGNORECASE)
DOCTOR_RX = _rx(rf"(?<![A-Za-z])(?:Dr|DR|Doctor)\.?\s+|(?<![{DEVA}])(?:डॉ\.?|डॉक्टर)\s*")
FACILITY_RX = _rx(rf"(?:(?:[A-Z][A-Za-z.&'’-]*|[{DEVA}]+)\s+){{0,4}}{L.FACILITY_WORDS}(?![A-Za-z])")
CAPS_FACILITY_RX = _rx(r"(?m)^[A-Z][A-Z .,&'-]{3,}(?:HOSPITAL|SADAN|PATHOLOGY|DIAGNOSTICS|CLINIC|LAB)[A-Z ,.'-]*$")
TITLE_SEQ_RX = _rx(r"(?<![A-Za-z.])[A-Z][a-z'’]{2,}(?:\s[A-Z][a-z'’]{2,}){1,2}(?![A-Za-z])")
_EPONYM_USE = re.compile(r"['’]s\b|\s+(?:disease|syndrome|palsy|sign|phenomenon|test|disorder|"
                        r"ulcer|tumou?r|lymphoma|reflex|criteria|scale|score)\b", re.IGNORECASE)
_ID_CAND = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9/\-.#]*[A-Za-z0-9](?![A-Za-z0-9])")
_ID_PART = re.compile(r"[A-Za-z0-9]+(?:[/\-][A-Za-z0-9]+)+")
_DIGIT_RUN = re.compile(r"(?<!\d)\d{5,}(?!\d)")
_LAT_WORD = re.compile(r"(?<![A-Za-z])[A-Za-z]+(?![A-Za-z])")
_DEVA_WORD = re.compile(rf"(?<![{DEVA}])[{DEVA}]+(?![{DEVA}])")
_ANY_WORD = re.compile(rf"(?<![\w{DEVA}])[\w{DEVA}][\w{DEVA}.]*")
_WORDCHAR = re.compile(rf"[\w{DEVA}]")
# "Label: value" / "Label - value" segments (line or "|"-separated) and <tag>value</tag>
LABEL_VALUE_RX = _rx(rf"(?:^|(?<=\|))[ \t]*([A-Za-z{DEVA}][A-Za-z{DEVA} .'’/#()]{{0,30}}?)[ \t]*(?:[:–]|\s-)[ \t]*((?:(?![ \t]{{2,}})[^|\n])+?)[ \t]*(?=\||$|[ \t]{{2,}})",
                     re.MULTILINE)
TAG_VALUE_RX = _rx(r"<([A-Za-z_][\w.-]{0,30})>([^<>\n]{1,120})</\1>")
RESIDENT_RX = _rx(rf"(?<![A-Za-z])(?:resident\s+of|r/o|residing\s+at)\s+|(?<![{DEVA}])निवासी\s+", re.IGNORECASE)
XML_TAG_RX = _rx(r"<[^>]{0,400}>")
_COMPLAINT_AFTER_CO = re.compile(r"\s*[:\-]?\s*[a-z]")


class Detector:
    """Runs every layer over a string and resolves overlaps."""

    def __init__(self, lex: RuntimeLexicon) -> None:
        self.lex = lex

    # ---------------------------------------------------------------- protected
    def protected(self, text: str) -> list[tuple[int, int]]:
        """Doctor names, facility names, admin places and markup: never redacted as names."""
        out: list[tuple[int, int]] = []
        for m in DOCTOR_RX.finditer(text):
            s = scan_name(text, m.end(), 4)
            if s:
                out.append((m.start(), s[1]))
        for rx in (FACILITY_RX, CAPS_FACILITY_RX):
            for m in rx.finditer(text):
                out.append((m.start(), m.end()))
        for m in ADMIN_RX.finditer(text):
            if not self.lex.keep_tehsil and TEHSIL_RX.match(text, m.start()):
                continue
            if not self.lex.keep_district and DISTRICT_RX.match(text, m.start()):
                continue
            s = scan_name(text, m.end(), 3)
            if s:
                out.append((m.start(), s[1]))
        for m in XML_TAG_RX.finditer(text):
            out.append((m.start(), m.end()))
        return out

    # ---------------------------------------------------------------- context names
    def context_names(self, text: str) -> list[Span]:
        """Names introduced by labels, relation markers, titles and honorifics."""
        lex = self.lex
        spans: list[Span] = []

        def add(pos: int, etype: str, rule: str, max_tok: int = 4) -> None:
            s = scan_name(text, pos, max_tok, lex=lex)
            if s and s[1] > s[0]:
                spans.append(Span(s[0], s[1], etype, rule))

        for m in PATIENT_LABEL_RX.finditer(text):
            add(m.end(), "PATIENT_NAME", "label.patient")
        for m in PT_DOT_RX.finditer(text):
            add(m.end(), "PATIENT_NAME", "label.pt")
        for m in RELATIVE_LABEL_RX.finditer(text):
            add(m.end(), "RELATIVE_NAME", "label.relative")
        for m in RELATION_RX.finditer(text):
            marker = m.group(0).strip().upper()
            if marker.startswith("C/O") or marker.startswith("CARE"):
                rest = text[m.end():m.end() + 40]
                first = re.match(r"([A-Za-zऀ-ॿ']+)", rest)
                if not first or _COMPLAINT_AFTER_CO.match(text, m.end()) or \
                        (lex.is_common_word(first.group(1)) and first.group(1).casefold() not in lex.name_latin):
                    continue
            add(m.end(), "RELATIVE_NAME", "relation.marker")
        for m in SUBJECT_OF_RELATION_RX.finditer(text):
            toks = m.group(1).split()
            if toks and not any(lex.is_common_word(t) and t.casefold() not in lex.name_latin for t in toks):
                spans.append(Span(m.start(1), m.end(1), "PATIENT_NAME", "relation.subject"))
        for m in RELATION_DEVA_RX.finditer(text):
            add(m.end(), "RELATIVE_NAME", "relation.deva")
        for m in PRE_TITLE_RX.finditer(text):
            add(m.end(), "PERSON_NAME", "title.pre", 3)
        for m in PRE_TITLE_DEVA_RX.finditer(text):
            add(m.end(), "PERSON_NAME", "title.pre.deva", 3)
        for m in POST_HON_RX.finditer(text):
            toks = m.group(1).split()
            keep = [t for t in toks]
            while keep and lex.is_common_word(keep[0]) and keep[0].casefold() not in lex.name_latin:
                keep.pop(0)
            if keep:
                s = m.start(1) + m.group(1).rfind(" ".join(keep))
                spans.append(Span(s, m.end(1), "PERSON_NAME", "honorific.post"))
        for m in HINGLISH_POSS_RX.finditer(text):
            toks = m.group(1).split()
            while toks and (lex.is_common_word(toks[0]) or toks[0].casefold() in L.NAME_STOPWORDS):
                toks.pop(0)
            if toks and all(not lex.is_common_word(t) for t in toks):
                s = m.start(1) + m.group(1).rfind(" ".join(toks))
                spans.append(Span(s, m.end(1), "PERSON_NAME", "hinglish.possessive"))
        for m in POST_HON_DEVA_RX.finditer(text):
            toks = m.group(1).split()
            if toks[-1] not in ("डॉक्टर", "मरीज़", "मरीज", "नर्स"):
                spans.append(Span(m.start(1), m.end(1), "PERSON_NAME", "honorific.post.deva"))
        for m in KIN_RX.finditer(text):
            add(m.end(), "RELATIVE_NAME", "kinship", 2)
        for m in KIN_DEVA_RX.finditer(text):
            add(m.end(), "RELATIVE_NAME", "kinship.deva", 2)
        for m in PATIENT_WORD_DEVA_RX.finditer(text):
            add(m.end(), "PATIENT_NAME", "patient.word.deva", 3)
        for m in PERSON_VERB_RX.finditer(text):
            add(m.end(), "PERSON_NAME", "verb.by", 3)
        for m in REPORT_OF_RX.finditer(text):
            add(m.end(), "PATIENT_NAME", "report.of")
        for m in WA_SENDER_RX.finditer(text):
            add(m.end(), "PERSON_NAME", "whatsapp.sender")
        return spans

    # ---------------------------------------------------------------- places & ids
    def labelled_places_ids(self, text: str) -> list[Span]:
        """Address / village labels and labelled hospital / insurance identifiers."""
        spans: list[Span] = []
        for m in ID_LABEL_RX.finditer(text):
            if any(c.isdigit() for c in m.group(1)):
                spans.append(Span(m.start(1), m.end(1), "MRN", "label.id"))
        for m in INS_LABEL_RX.finditer(text):
            if any(c.isdigit() for c in m.group(1)):
                spans.append(Span(m.start(1), m.end(1), "INSURANCE_ID", "label.insurance"))
        for m in ADDRESS_LABEL_RX.finditer(text):
            eol = text.find("\n", m.end())
            spans.extend(address_spans(text, m.end(), len(text) if eol < 0 else eol, self.lex.keep_tehsil,
                                       self.lex.keep_district))
        for m in RESIDENT_RX.finditer(text):
            s2 = scan_name(text, m.end(), 3)
            if s2:
                spans.append(Span(s2[0], s2[1], "VILLAGE", "label.resident"))
        for rx in (LABEL_VALUE_RX, TAG_VALUE_RX):
            for m in rx.finditer(text):
                spans.extend(role_spans(text, m.group(1), m.start(2), m.end(2), self.lex.keep_tehsil,
                                        self.lex.keep_district))
        if not self.lex.keep_district:
            for m in DISTRICT_RX.finditer(text):
                s2 = scan_name(text, m.end(), 3)
                if s2:
                    spans.append(Span(m.start(), s2[1], "TEHSIL", "label.district"))
        if not self.lex.keep_tehsil:
            for m in TEHSIL_RX.finditer(text):
                s2 = scan_name(text, m.end(), 3)
                if s2:
                    spans.append(Span(m.start(), s2[1], "TEHSIL", "label.tehsil"))
        for m in VILLAGE_LABEL_RX.finditer(text):
            s = scan_name(text, m.end(), 3)
            if s:
                spans.append(Span(s[0], s[1], "VILLAGE", "label.village"))
        return spans

    # ---------------------------------------------------------------- lexicon
    def lexicon_spans(self, text: str, any_case: bool) -> list[Span]:
        """Occurrences of names, IDs and places learned from this dataset (token-indexed)."""
        lex, spans = self.lex, []
        if not lex._compiled:
            return spans
        if lex.id_set or lex.core_set:
            for m in _ID_CAND.finditer(text):
                tok = m.group(0)
                if tok.upper() in lex.id_set:
                    spans.append(Span(m.start(), m.end(), "MRN", "lex.id"))
                    continue
                for sub in _ID_PART.finditer(tok):  # an ID embedded in a longer token
                    if sub.group(0).upper() in lex.id_set:
                        spans.append(Span(m.start() + sub.start(), m.start() + sub.end(), "MRN", "lex.id"))
            if lex.core_set:
                for m in _DIGIT_RUN.finditer(text):
                    if m.group(0) in lex.core_set:
                        spans.append(Span(m.start(), m.end(), "MRN", "lex.idcore"))
        if lex.name_set:
            for m in _LAT_WORD.finditer(text):
                tok = m.group(0)
                low = tok.casefold()
                if low not in lex.name_set:
                    continue
                title = tok[0].isupper() and not tok.isupper()
                if not any_case and low in L.CLINICAL_WORDS and _EPONYM_USE.match(text, m.end()):
                    continue  # "Wilson's disease", "Graves disease": an eponym, not a person
                if any_case or title:
                    if not any_case and lex.is_common_word(tok):
                        continue
                    spans.append(Span(m.start(), m.end(), "PERSON_NAME", "lex.name"))
        if lex.deva_set:
            for m in _DEVA_WORD.finditer(text):
                if m.group(0) in lex.deva_set:
                    spans.append(Span(m.start(), m.end(), "PERSON_NAME", "lex.name.deva"))
        if not lex.keep_tehsil and lex.tehsil_rx is not None:
            for m in lex.tehsil_rx.finditer(text):
                spans.append(Span(m.start(), m.end(), "TEHSIL", "lex.tehsil"))
        if lex.place_first:
            low_text = text.casefold()
            for m in _ANY_WORD.finditer(low_text):
                cands = lex.place_first.get(m.group(0))
                if not cands:
                    continue
                for p in cands:
                    end = m.start() + len(p)
                    if low_text.startswith(p, m.start()) and not (end < len(low_text) and _WORDCHAR.match(low_text[end])):
                        spans.append(Span(m.start(), end, "VILLAGE", "lex.place"))
                        break
        return spans

    def heuristic_names(self, text: str) -> list[Span]:
        """2–3 capitalised tokens that are not vocabulary of this dataset."""
        out = []
        for m in TITLE_SEQ_RX.finditer(text):
            toks = m.group(0).split()
            if all(not self.lex.is_common_word(t) and t.casefold() not in self.lex.protected
                   and t.casefold() not in L.NAME_STOPWORDS for t in toks):
                out.append(Span(m.start(), m.end(), "PERSON_NAME", "heur.title"))
        return out

    # ---------------------------------------------------------------- main
    def detect(self, text: str, mode: str = "text") -> list[Span]:
        """All PII spans in ``text``; ``mode`` is ``text``, ``name`` (file / key) or ``meta``."""
        if not text:
            return []
        t = ascii_digits(text)
        cands: list[Span] = []
        for rule in RULES:
            for m in rule.regex.finditer(t):
                cands.append(Span(m.start(rule.group), m.end(rule.group), rule.entity, rule.rule_id))
        any_case = mode != "text"
        cands += self.lexicon_spans(t, any_case)
        if mode == "text":
            cands += self.context_names(t)
            cands += self.labelled_places_ids(t)
            cands += self.heuristic_names(t)
        prot = self.protected(t) if mode == "text" else []
        kept = [c for c in cands if not (
            (c.etype in NAME_TYPES or c.etype in PLACE_TYPES)
            and any(p[0] <= c.start and c.end <= p[1] or (c.start < p[1] and p[0] < c.end and
                    c.rule.startswith(("lex.", "heur.", "honorific", "title"))) for p in prot))]
        return resolve([expand_name(t, c) if c.etype in NAME_TYPES else c for c in kept])


_GENERIC_ALT = "|".join(sorted((re.escape(g) for g in L.GENERIC_NAME_TOKENS), key=len, reverse=True))
_EXPAND_LEFT = re.compile(rf"(?:(?<![\w{DEVA}])(?:{_GENERIC_ALT}|{L.PRE_TITLES}|{L.PRE_TITLES_DEVA})\.?\s)+$",
                          re.IGNORECASE)
_EXPAND_RIGHT = re.compile(rf"^(?:\s(?:{_GENERIC_ALT}|{L.POST_HONORIFICS}|{L.POST_HONORIFICS_DEVA})\.?(?![\w{DEVA}]))+",
                           re.IGNORECASE)


def expand_name(text: str, s: Span) -> Span:
    """Grow a name span over adjacent generic parts and honorifics (``Mohd.``, ``ji``, ``amma``).

    They identify no one alone, but next to a removed name they are residue of it.
    """
    start, end = s.start, s.end
    m = _EXPAND_LEFT.search(text[max(0, start - 40):start])
    if m:
        start -= len(m.group(0))
    m = _EXPAND_RIGHT.match(text[end:end + 40])
    if m:
        end += len(m.group(0))
    return Span(start, end, s.etype, s.rule) if (start, end) != (s.start, s.end) else s


_ROLE_ETYPE = {"patient_name": "PATIENT_NAME", "first_name": "PATIENT_NAME", "last_name": "PATIENT_NAME",
               "local_name": "PATIENT_NAME", "person_name": "PERSON_NAME", "relative_name": "RELATIVE_NAME",
               "guardian": "RELATIVE_NAME", "phone": "PHONE", "email": "EMAIL", "aadhaar": "AADHAAR",
               "abha": "ABHA_NUMBER", "abha_address": "ABHA_ADDRESS", "pan": "PAN", "mrn": "MRN",
               "insurance": "INSURANCE_ID", "village": "VILLAGE", "locality": "ADDRESS", "house": "ADDRESS",
               "pin": "PIN"}


def role_spans(text: str, label: str, start: int, end: int, keep_tehsil: bool = True,
               keep_district: bool = True) -> list[Span]:
    """Spans for a labelled value whose label the field classifier recognises (any language)."""
    from .columns import ADDRESS, classify_label

    role = classify_label(label.strip())
    if role is None:
        return []
    if role == ADDRESS:
        return address_spans(text, start, end, keep_tehsil, keep_district)
    etype = _ROLE_ETYPE.get(role)
    if etype is None:
        return []
    value = text[start:end]
    if etype in ("PATIENT_NAME", "PERSON_NAME", "RELATIVE_NAME"):
        s = scan_name(text, start, 4)
        return [Span(s[0], s[1], etype, "label.field")] if s else []
    if etype == "PIN":
        m = re.search(r"[1-8]\d{5}", value)
        return [Span(start + m.start(), start + m.end(), "PIN", "label.field")] if m else []
    if etype in ("PHONE", "AADHAAR", "ABHA_NUMBER", "MRN", "INSURANCE_ID") and not re.search(r"\d", value):
        return []
    return [Span(start, end, etype, "label.field")]


def address_spans(text: str, start: int, end: int, keep_tehsil: bool = True,
                  keep_district: bool = True) -> list[Span]:
    """Spans for an address value: every comma segment except Tehsil / District clauses.

    A trailing ``- 229073`` PIN becomes a PIN span (generalised, not deleted).
    """
    spans: list[Span] = []
    seg_start = start
    value = text[start:end]
    pin = re.search(r"[-–,]?\s*([1-8]\d{5})\s*$", value)
    limit = start + (pin.start() if pin else len(value))
    if pin:
        spans.append(Span(start + pin.start(1), start + pin.end(1), "PIN", "address.pin"))
    for m in re.finditer(r",|$", text[start:limit]):
        seg_end = start + m.start()
        seg = text[seg_start:seg_end]
        admin = ADMIN_RX.match(seg.strip()) and (keep_tehsil or not TEHSIL_RX.match(seg.strip())) \
            and (keep_district or not DISTRICT_RX.match(seg.strip()))
        if seg.strip() and not admin and not re.fullmatch(r"\s*(?:India|UP|U\.P\.)\s*", seg):
            lead = len(seg) - len(seg.lstrip())
            trail = len(seg.rstrip())
            spans.append(Span(seg_start + lead, seg_start + trail, "ADDRESS", "label.address"))
        seg_start = seg_end + 1
        if m.group(0) == "":
            break
    return spans


_GUESS_RULES = ("heur.", "lex.name", "honorific", "title.", "hinglish.")


def _rank(s: Span) -> int:
    """Strong identifiers first; among names and places an explicit label beats a guess."""
    base = _PRIORITY.get(s.etype, 0)
    if s.etype in NAME_TYPES or s.etype in PLACE_TYPES:
        base = 3 if s.rule.startswith(_GUESS_RULES) else 6.5  # type: ignore[assignment]
    return base


def resolve(spans: list[Span]) -> list[Span]:
    """Merge overlapping spans; the merged span takes the highest-priority type."""
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: (s.start, -s.end))
    out: list[Span] = [spans[0]]
    for s in spans[1:]:
        last = out[-1]
        if s.start < last.end:
            best = max((last, s), key=lambda x: (_rank(x), x.end - x.start))
            out[-1] = Span(last.start, max(last.end, s.end), best.etype, best.rule)
        else:
            out.append(s)
    return out
