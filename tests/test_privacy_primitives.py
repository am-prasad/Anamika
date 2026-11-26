"""Pseudonym, date-shift, age-band and checksum primitives."""
from __future__ import annotations

import datetime as dt
import hashlib

import pytest

from anamika.detect.patterns import verhoeff_valid
from anamika.link.pseudonym import CROCKFORD, assign, pseudonym
from anamika.privacy.ages import age_band
from anamika.privacy.dates import shift_date, shift_days
from anamika.safety import Keyring

K1, K2 = Keyring.from_secret(b"practice"), Keyring.from_secret(b"another-secret")


def test_pseudonym_format_and_stability() -> None:
    p = pseudonym(K1, "anchor-1")
    assert p.startswith("PSN-") and len(p) == 10 and all(c in CROCKFORD for c in p[4:])
    assert p == pseudonym(K1, "anchor-1") != pseudonym(K2, "anchor-1")


def test_pseudonym_is_not_a_plain_hash_of_the_anchor() -> None:
    anchor = "SNJ/26/064127"
    p = pseudonym(K1, anchor)[4:].lower()
    for h in (hashlib.md5, hashlib.sha1, hashlib.sha256):
        assert p not in h(anchor.encode()).hexdigest()


def test_assign_unique_and_order_independent() -> None:
    anchors = [f"a{i}" for i in range(3000)]
    m1, m2 = assign(K1, anchors), assign(K1, list(reversed(anchors)))
    assert m1 == m2 and len(set(m1.values())) == len(anchors)


@pytest.mark.parametrize("key", ["PSN-AAAAAA", "PSN-7Q2K9D", "record:x:3"])
def test_shift_range_and_sign(key: str) -> None:
    d = shift_days(K1, key, 30, 365)
    assert 30 <= abs(d) <= 365
    assert shift_days(K1, key, 30, 365) == d


def test_shift_changes_with_secret() -> None:
    same = sum(shift_days(K1, f"p{i}") == shift_days(K2, f"p{i}") for i in range(200))
    assert same < 10


def test_shift_preserves_length_of_stay() -> None:
    off = shift_days(K1, "PSN-X")
    adm, dis = dt.date(2026, 3, 1), dt.date(2026, 3, 10)
    assert (shift_date(dis, off) - shift_date(adm, off)).days == 9


def test_shift_multiple_of_seven_keeps_weekday() -> None:
    off = shift_days(K1, "PSN-X", multiple_of_7=True)
    assert off % 7 == 0 and off != 0


@pytest.mark.parametrize("age,band", [(0, "0-4"), (47, "45-49"), (49, "45-49"), (89, "85-89"),
                                      (90, "90+"), (103, "90+")])
def test_age_band_contains_true_age(age: int, band: str) -> None:
    assert age_band(age) == band


def test_verhoeff() -> None:
    assert verhoeff_valid("2363")         # canonical test vector
    assert not verhoeff_valid("2364")
    assert not verhoeff_valid("12a4")
