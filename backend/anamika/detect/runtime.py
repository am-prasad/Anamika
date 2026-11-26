"""Run-time lexicon: what *this* input teaches us about its own people and places.

Pass A feeds it every structured name, identifier, village / locality / house value,
doctor, tehsil and district it classifies, plus names harvested from unambiguous text
labels (``Name:``, ``S/o``, ``नाम:``…). Pass B then finds those same values anywhere —
free text, export metadata, JSON keys, CSV headers, file names, base64 payloads — which
is how a name typed once in a registration file is removed from a Hinglish nursing note.

Nothing here is shipped with the code: each dataset builds its own lexicon, so the
approach transfers to unseen patients and names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import lexicon as L
from .patterns import ascii_digits

_LAT = re.compile(r"[A-Za-z][A-Za-z'’]+")
_DEVA = re.compile(r"[ऀ-ॣ॰-ॿ]+")
_LOWER_WORD = re.compile(r"(?<![\w@./\\:-])[a-z]{3,}(?![\w@./\\:-])")
_DEVA_COMMON = frozenset("""
का की के को ने से है था थी में पर और या भी नहीं हैं दिन बुखार दर्द मरीज़ मरीज डॉक्टर नर्स अस्पताल
वर्ष साल पुरुष महिला पता ग्राम तहसील जिला मोबाइल नाम उम्र आयु तारीख निदान दवा जांच भर्ती छुट्टी
""".split())


def _norm_id(v: str) -> str:
    return ascii_digits(v).strip().upper()


@dataclass
class RuntimeLexicon:
    """Accumulates dataset-specific vocabularies, then compiles matchers."""

    name_latin: set[str] = field(default_factory=set)
    name_deva: set[str] = field(default_factory=set)
    ids: set[str] = field(default_factory=set)
    id_cores: set[str] = field(default_factory=set)
    places: set[str] = field(default_factory=set)        # village / locality / house values
    protected: set[str] = field(default_factory=set)     # doctor, tehsil, district tokens
    protected_deva: set[str] = field(default_factory=set)
    lower_vocab: set[str] = field(default_factory=set)
    safe_vocab: set[str] = field(default_factory=set)
    _compiled: bool = False

    def __post_init__(self) -> None:
        self.name_rx = self.deva_rx = self.id_rx = self.core_rx = self.place_rx = None

    # ---------------------------------------------------------------- feeding
    def add_name(self, value: str) -> None:
        """Register a person's name (any script)."""
        for tok in _LAT.findall(value or ""):
            t = tok.casefold().strip("'’")
            if len(t) >= 3 and t not in L.GENERIC_NAME_TOKENS:
                self.name_latin.add(t)
        for tok in _DEVA.findall(value or ""):
            if len(tok) >= 2 and tok not in L.GENERIC_NAME_TOKENS and tok not in _DEVA_COMMON:
                self.name_deva.add(tok)

    def add_id(self, value: str) -> None:
        """Register a hospital identifier (UHID, IPD no., policy no., …)."""
        v = _norm_id(value or "")
        if len(v) >= 5 and any(c.isdigit() for c in v):
            self.ids.add(v)
            for core in re.findall(r"\d{5,}", v):
                self.id_cores.add(core)

    def add_place(self, value: str) -> None:
        """Register a village / locality / house value to remove wherever it appears."""
        v = " ".join((value or "").split())
        if len(v) >= 4 and not v.isdigit():
            self.places.add(v.casefold())

    def add_protected(self, value: str) -> None:
        """Register tokens that must survive (doctor names, tehsil, district)."""
        for tok in _LAT.findall(value or ""):
            if len(tok) >= 3:
                self.protected.add(tok.casefold())
        for tok in _DEVA.findall(value or ""):
            self.protected_deva.add(tok)

    def add_safe_phrase(self, value: str) -> None:
        """Register clinical / administrative vocabulary seen in non-PII fields."""
        for tok in _LAT.findall(value or ""):
            self.safe_vocab.add(tok.casefold())

    def observe_text(self, text: str) -> None:
        """Learn which words occur in lower case (common words, not names)."""
        for w in _LOWER_WORD.findall(text or ""):
            self.lower_vocab.add(w)

    # ---------------------------------------------------------------- compile
    def compile(self) -> None:
        """Freeze the vocabularies into regular expressions."""
        names = sorted(self.name_latin,
                       key=lambda s: (-len(s), s))
        self.name_rx = _alt(names, r"(?<![A-Za-z])", r"(?![A-Za-z])", re.IGNORECASE)
        deva = sorted(self.name_deva, key=lambda s: (-len(s), s))
        self.deva_rx = _alt(deva, r"(?<![ऀ-ॿ])", r"(?![ऀ-ॿ])", 0)
        ids = sorted(self.ids, key=lambda s: (-len(s), s))
        self.id_rx = _alt(ids, r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])", re.IGNORECASE)
        cores = sorted(self.id_cores, key=lambda s: (-len(s), s))
        self.core_rx = _alt(cores, r"(?<!\d)", r"(?!\d)", 0)
        places = sorted((p for p in self.places if p not in self.protected), key=lambda s: (-len(s), s))
        self.place_rx = _alt(places, r"(?<![\wऀ-ॿ])", r"(?![\wऀ-ॿ])", re.IGNORECASE)
        self._compiled = True

    def is_common_word(self, tok: str) -> bool:
        """A token that is ordinary vocabulary in this dataset (never treated as a name)."""
        t = tok.casefold()
        if t in self.name_latin and t not in self.lower_vocab:
            return False  # learned from a structured name field: a name, not vocabulary
        return (t in self.lower_vocab or t in L.CLINICAL_WORDS or t in self.safe_vocab
                or t in L.MONTHS)


def _alt(items: list[str], left: str, right: str, flags: int) -> re.Pattern[str] | None:
    if not items:
        return None
    return re.compile(left + "(?:" + "|".join(re.escape(i) for i in items) + ")" + right, flags)
