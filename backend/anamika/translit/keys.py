"""Cross-script phonetic keys: the same person or village in Latin, Devanagari or Hinglish.

``शाहिद`` → ITRANS ``shAhida`` → folded ``sahid`` → skeleton ``shd``; ``Shahid`` → ``shd``.
Folding collapses the usual transliteration variance (long vowels, aspirates, ``w/v``,
``ph/f``, ``z/j``, anusvara, the inherent final ``a``) and the skeleton keeps the first letter
plus consonants, which is where Indian name spellings agree. Generic parts
(``Mohd``, ``Kumar``, ``Devi``, ``ji``…) are dropped and tokens are sorted, so word order
does not matter.

Keys are only ever used *together* with a second clue (village, relative, DOB) and under
the linker's cannot-link constraints — never alone.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from ..detect.lexicon import GENERIC_NAME_TOKENS

_DEVA = re.compile(r"[ऀ-ॿ]")
_FOLD = [("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ou", "au"),
         ("w", "v"), ("ph", "f"), ("z", "j"), ("q", "k"), ("x", "ks"), ("ck", "k"),
         ("kh", "k"), ("gh", "g"), ("chh", "c"), ("ch", "c"), ("jh", "j"), ("th", "t"),
         ("dh", "d"), ("bh", "b"), ("sh", "s"), ("ksh", "ks")]


_WEAK = {"mohamad", "muhamad", "mohd", "md", "kumar", "kumari", "devi", "sing", "sinh", "singh",
         "lal", "bai", "ben", "bano", "begum", "kaur"}


def to_latin(token: str) -> str:
    """Devanagari token → lower-case Latin (ITRANS-based); Latin tokens pass through."""
    if not _DEVA.search(token):
        return token.casefold()
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate

    t = transliterate(token, sanscript.DEVANAGARI, sanscript.ITRANS)
    t = t.replace(".N", "n").replace("~N", "n").replace("~n", "n").replace("M", "n")
    t = t.replace("RRi", "ri").replace(".D", "d").replace(".Dh", "d").replace("^", "")
    return t.casefold()


@lru_cache(maxsize=65536)
def fold(token: str) -> str:
    """Spelling-variance folding of one Latin token."""
    t = unicodedata.normalize("NFKD", token.casefold())
    t = re.sub(r"[^a-z]", "", t)
    for a, b in _FOLD:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)
    if len(t) > 3 and t.endswith("a") and t[-2] not in "aeiou":
        t = t[:-1]  # inherent vowel of Devanagari transliteration: "shahida" → "shahid"
    return t


def skeleton(token: str) -> str:
    """First letter + consonants of the folded token (``sunita`` → ``snt``)."""
    f = fold(to_latin(token))
    if not f:
        return ""
    return f[0] + re.sub(r"[aeiouy]", "", f[1:])


def name_key(value: str | None) -> str | None:
    """Order-independent cross-script key for a person's name (``None`` if nothing left)."""
    if not value:
        return None
    toks = re.findall(r"[A-Za-z]+|[ऀ-ॿ]+", value)
    keys = sorted({skeleton(t) for t in toks
                   if t.casefold() not in GENERIC_NAME_TOKENS and t not in GENERIC_NAME_TOKENS
                   and fold(to_latin(t)) not in _WEAK})
    keys = [k for k in keys if len(k) >= 2]
    return " ".join(keys) if keys else None


def place_key(value: str | None) -> str | None:
    """Cross-script key for a village / locality name."""
    if not value:
        return None
    toks = re.findall(r"[A-Za-z]+|[ऀ-ॿ]+", value)
    keys = [skeleton(t) for t in toks if len(t) > 1]
    keys = [k for k in keys if k]
    return " ".join(sorted(keys)) if keys else None


def first_key(value: str | None) -> str | None:
    """Key of the first non-generic given name (``Md. Shahid Ansari`` → key of ``Shahid``)."""
    if not value:
        return None
    for t in re.findall(r"[A-Za-z]+|[\u0900-\u097F]+", value):
        if t.casefold() in GENERIC_NAME_TOKENS or t in GENERIC_NAME_TOKENS or fold(to_latin(t)) in _WEAK:
            continue
        k = skeleton(t)
        if len(k) >= 2:
            return k
    return None
