#!/usr/bin/env python3
"""Leak scanner: searches a release and its side channels for known PII and canaries.

Development tool (not part of the pipeline). It reads the practice answer key, derives
the same kind of *keys* the official scorer uses, and searches every scanned location:

* **name tokens** — identifying tokens of patient / relative / canary names (generic
  tokens such as Devi, Kumar, Md., ji are ignored), word-bounded, plus a Latin
  transliteration of Devanagari tokens;
* **digit cores** — Aadhaar, phone, ABHA, UHID/IPD digits, matched across separators,
  Devanagari digits and JSON numbers;
* **exact text** — email, PAN, insurance IDs, house / locality / landmark / village;
* **DOB** — the true birth date rendered in common formats.

Both sides are normalised (NFKC, zero-width removal, Indic digits → ASCII, diacritics
stripped, casefold); base64, ``\\uXXXX``, HTML entities and %-escapes are decoded and
appended, mirroring the official leak counter.

Per input file it follows the scorer's rule ``leaked = clamp(out − allowed, 0, pii)``
where *allowed* are occurrences inside preserve-probes (e.g. "Dr. Ramesh"). Side
channels (``report.json``, ``records.jsonl``, ``logs/``, TMP dirs, captured stdout) get
zero tolerance. **Values are never printed**: output lists types, channels, counts and
SHA-256 prefixes of the affected files only.

Usage::

    python tools/leak_scan.py --output OUT [--extra DIR_OR_FILE ...] [--truth truth.json]

Exit code 0 when no leak and no canary is found, 1 otherwise.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_KIT = Path(os.environ.get("ANAMIKA_TOOLKIT",
                                  Path(__file__).resolve().parents[3] / "Secret-Wards-ToolKit"))

GENERIC_TOKENS = {
    "devi", "kumar", "kumari", "kr", "md", "mohd", "ji", "sahab", "saab", "sahib", "smt",
    "shri", "sri", "shree", "mr", "mrs", "ms", "miss", "km", "baby", "master", "didi",
    "bhai", "bhaiya", "behen", "behenji", "bibi", "begum", "bai", "ben", "the", "jee", "sahib",
    "aunty", "auntie", "uncle", "amma", "babu", "chacha", "chachi", "dada", "dadi", "nana", "nani",
    "mausi", "bua", "beta",
    "देवी", "कुमार", "कुमारी", "जी", "साहब", "श्री", "श्रीमती", "मो", "दीदी", "भैया", "भाई",
    "अम्मा", "बाबू", "चाचा", "चाची", "दादा", "दादी",
}
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_INDIC_DIGITS = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}
_HOMOGLYPHS = str.maketrans("АВЕКМНОРСТХаеорсхуіІ", "ABEKMHOPCTXaeopcxyiI")
_TOKEN = re.compile(r"(?:[^\W\d_]|[ऀ-ॣ॰-ॿ])+")
_B64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}){8,}")
_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")
# Word boundary on letters/digits only, so "_" and "\" separate tokens (paths, keys).
_WB_L = r"(?<![^\W_]|[ऀ-ॿ])"
_WB_R = r"(?![^\W_]|[ऀ-ॿ])"


def normalise(s: str) -> str:
    """Scorer-style normalisation of text for matching."""
    s = unicodedata.normalize("NFKC", s).translate(_ZW).translate(_INDIC_DIGITS)
    s = s.translate(_HOMOGLYPHS)
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not (unicodedata.combining(c) and ord(c) < 0x0900))
    s = unicodedata.normalize("NFC", s)
    return " ".join(s.casefold().split())


def expand_hidden(text: str) -> str:
    """Append decoded base64 / hex / \\u / HTML / %-encoded payloads found in ``text``."""
    extra: list[str] = []
    for m in _B64.finditer(text):
        tok = m.group(0)
        try:
            extra.append(base64.b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8", "ignore"))
        except (binascii.Error, ValueError):
            pass
    for m in _HEX.finditer(text):
        try:
            extra.append(bytes.fromhex(m.group(0)).decode("utf-8", "ignore"))
        except ValueError:
            pass
    if "\\u" in text:
        extra.append(_UESC.sub(lambda m: chr(int(m.group(1), 16)), text))
    if "&" in text:
        extra.append(html.unescape(text))
    if "%" in text:
        extra.append(urllib.parse.unquote(text))
    return text + ("\n" + "\n".join(extra) if extra else "")


def read_norm(p: Path) -> str:
    """Read ``p`` leniently (any encoding), expand hidden payloads, normalise."""
    raw = p.read_bytes()[: 64 * 1024 * 1024]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    return normalise(expand_hidden(text))


def _deva_to_latin(tok: str) -> str | None:
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
    except ImportError:
        return None
    lat = transliterate(tok, sanscript.DEVANAGARI, sanscript.HK).lower()
    lat = re.sub(r"[^a-z]", "", lat)
    return lat if len(lat) >= 3 else None


# --------------------------------------------------------------------------- keys


class Key:
    """One searchable key derived from a PII mention."""

    __slots__ = ("kind", "value", "rx", "etype", "channel", "script", "canary")

    def __init__(self, kind: str, value: str, etype: str, channel: str, script: str) -> None:
        self.kind, self.value, self.etype = kind, value, etype
        self.channel, self.script, self.canary = channel, script, etype == "CANARY"
        if kind == "digits":
            body = r"[\s\-./,:]*".join(re.escape(d) for d in value)
            self.rx = re.compile(r"(?<!\d)" + body + r"(?!\d)")
        elif kind in ("token", "translit"):
            self.rx = re.compile(_WB_L + re.escape(value) + _WB_R)
        else:
            self.rx = re.compile(re.escape(value))

    def count(self, hay: str) -> int:
        """Number of occurrences of this key in normalised text ``hay``."""
        return len(self.rx.findall(hay)) if hay else 0

    def ident(self) -> tuple[str, str]:
        return (self.kind, self.value)


def _dob_forms(iso: str) -> list[str]:
    d = dt.date.fromisoformat(iso)
    mon = d.strftime("%b").lower()
    month = d.strftime("%B").lower()
    return sorted({
        f"{d.day:02d}/{d.month:02d}/{d.year}", f"{d.day:02d}-{d.month:02d}-{d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year}", f"{d.month:02d}/{d.day:02d}/{d.year}",
        d.isoformat(), f"{d.day} {mon} {d.year}", f"{d.day:02d}-{mon}-{d.year}",
        f"{d.day} {month} {d.year}", f"{d.day:02d} {month} {d.year}",
    })


def keys_for(entity: dict) -> list[Key]:
    """Derive the scorer-style keys of one truth entity."""
    etype, match = entity["type"], entity["match"]
    ch, sc = entity["channel"], entity["script"]
    surface = normalise(entity["surface"])
    out: list[Key] = []
    if match == "name":
        for tok in _TOKEN.findall(surface):
            if len(tok) < 3 or tok in GENERIC_TOKENS:
                continue
            out.append(Key("token", tok, etype, ch, sc))
            if re.search(r"[ऀ-ॿ]", tok):
                lat = _deva_to_latin(tok)
                if lat:
                    out.append(Key("translit", lat, etype, ch, sc))
    elif match in ("digits", "digits_exact"):
        digits = re.sub(r"\D", "", normalise(entity.get("key") or entity["surface"]))
        if len(digits) >= 5:
            out.append(Key("digits", digits, etype, ch, sc))
    elif match == "dob":
        for form in _dob_forms(entity["key"]):
            out.append(Key("text", form, etype, ch, sc))
    else:
        val = normalise(entity.get("key") or entity["surface"])
        if len(val) >= 3:
            out.append(Key("text", val, etype, ch, sc))
    return out


# --------------------------------------------------------------------------- scan


def sha12(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def scan(out_dir: Path, input_dir: Path, truth_path: Path, extras: list[Path]) -> dict:
    """Scan ``out_dir`` (+ ``extras``) against the answer key; return a summary dict.

    ``input_dir`` is the raw input the release was produced from (needed for the
    scorer's "allowed occurrences" rule); ``truth_path`` is the matching answer key.
    """
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    inp = input_dir
    san = out_dir / "sanitized"
    try:
        report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {"files": []}
    declared = {e.get("input_sha256"): e.get("output") for e in report.get("files") or []}

    leaks: Counter[tuple[str, str]] = Counter()      # (type, channel) -> leaked mentions
    totals: Counter[tuple[str, str]] = Counter()
    by_script: Counter[str] = Counter()
    tot_script: Counter[str] = Counter()
    files_hit: dict[str, Counter[str]] = defaultdict(Counter)
    all_keys: dict[tuple[str, str], Key] = {}
    translit_hits = 0

    for rel, f in truth["files"].items():
        out_rel = str(declared.get(f["sha256"]) or f"sanitized/{rel}").replace("sanitized/", "", 1)
        out_path = san / out_rel
        exported = out_path.is_file() and declared.get(f["sha256"]) is not None
        src = inp / rel
        in_text = read_norm(src) if src.is_file() else ""
        out_text = read_norm(out_path) if exported else ""
        in_name, out_name = normalise(rel), normalise(out_rel) if exported else ""
        probes = [normalise(p["text"]) for u in f["units"].values() for p in u.get("preserve") or []]
        for u in f["units"].values():
            for e in u["entities"]:
                ks = keys_for(e)
                for k in ks:
                    all_keys.setdefault(k.ident(), k)
                if e["type"] == "CANARY":
                    continue
                totals[(e["type"], e["channel"])] += 1
                tot_script[e["script"]] += 1
                if not exported and e["channel"] != "filename":
                    continue
                hay_in = in_name if e["channel"] == "filename" else in_text
                hay_out = out_name if e["channel"] == "filename" else out_text
                fracs = []
                for k in ks:
                    if k.kind == "translit":
                        if k.count(hay_out):
                            translit_hits += 1
                        continue
                    allowed = sum(k.count(p) for p in probes)
                    pii = max(k.count(hay_in) - allowed, 1)
                    leaked = min(max(k.count(hay_out) - allowed, 0), pii)
                    fracs.append(leaked / pii)
                if fracs and sum(fracs) / len(fracs) > 0:
                    leaks[(e["type"], e["channel"])] += 1
                    by_script[e["script"]] += 1
                    files_hit[sha12(rel)][e["type"]] += 1

    # side channels: zero tolerance for any key
    side: Counter[str] = Counter()
    canary_keys = [k for k in all_keys.values() if k.canary and k.kind == "token"]
    canary_hits: set[str] = set()
    corpus_parts: list[tuple[str, str]] = []
    for name in ("report.json", "records.jsonl"):
        p = out_dir / name
        if p.is_file():
            corpus_parts.append((name, read_norm(p)))
    for root in [out_dir / "logs", *extras]:
        if root.is_file():
            corpus_parts.append(("extra", read_norm(root)))
        elif root.is_dir():
            for dp, _, fn in os.walk(root):
                for n in fn:
                    corpus_parts.append(("extra", normalise(n) + "\n" + read_norm(Path(dp) / n)))
    names_blob = "\n".join(normalise(p.relative_to(out_dir).as_posix())
                           for p in out_dir.rglob("*") if p.is_file())
    corpus_parts.append(("output_names", names_blob))
    strong = [k for k in all_keys.values() if k.kind in ("digits", "text") and not k.canary]
    for chan, text in corpus_parts:
        for k in strong:
            if k.count(text):
                side[chan] += 1
    # canaries anywhere under the output folder and extras
    everything = "\n".join(t for _, t in corpus_parts)
    if san.is_dir():
        everything += "\n" + "\n".join(read_norm(p) for p in san.rglob("*") if p.is_file())
    for k in canary_keys:
        if k.count(everything):
            canary_hits.add(k.value)

    return {
        "leaked_mentions": sum(leaks.values()),
        "total_mentions": sum(totals.values()),
        "by_type": {f"{t}/{c}": [leaks[(t, c)], totals[(t, c)]] for (t, c) in sorted(totals)},
        "by_script": {s: [by_script[s], tot_script[s]] for s in sorted(tot_script)},
        "side_channel_hits": dict(side),
        "canary_tokens_found": len(canary_hits),
        "canary_tokens_total": len({k.value for k in canary_keys}),
        "translit_name_hits": translit_hits,
        "files_with_leaks": len(files_hit),
        "worst_files": sorted(((sum(c.values()), s) for s, c in files_hit.items()), reverse=True)[:10],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Anamika leak scanner (never prints values)")
    ap.add_argument("--output", required=True, help="pipeline output folder")
    ap.add_argument("--kit", default=str(DEFAULT_KIT), help="organiser toolkit folder")
    ap.add_argument("--input", default=None, help="raw input dir (default: <kit>/dev/input)")
    ap.add_argument("--truth", default=None, help="truth.json (default: <kit>/dev/truth/truth.json)")
    ap.add_argument("--extra", nargs="*", default=[], help="more dirs/files: logs, TMPDIR, stdout capture")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    a = ap.parse_args()
    kit = Path(a.kit)
    res = scan(Path(a.output), Path(a.input or kit / "dev" / "input"), Path(a.truth or kit / "dev" / "truth" / "truth.json"),
               [Path(x) for x in a.extra])
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        lm, tm = res["leaked_mentions"], res["total_mentions"]
        print(f"LEAK SCAN  mentions leaked {lm}/{tm} ({100 * lm / max(tm, 1):.1f}%)  "
              f"canaries {res['canary_tokens_found']}/{res['canary_tokens_total']} tokens  "
              f"side-channel hits {sum(res['side_channel_hits'].values())}")
        for key, (l, t) in res["by_type"].items():
            if l:
                print(f"  {key:<34} {l:>4}/{t}")
        print("  by script: " + ", ".join(f"{s} {l}/{t}" for s, (l, t) in res["by_script"].items()))
        if res["side_channel_hits"]:
            print("  side channels: " + ", ".join(f"{c}={n}" for c, n in res["side_channel_hits"].items()))
        print(f"  transliterated name-token hits (informational): {res['translit_name_hits']}")
        print(f"  files with leaks: {res['files_with_leaks']} (worst by sha12: "
              + ", ".join(f"{s}:{n}" for n, s in res["worst_files"][:5]) + ")")
    clean = res["leaked_mentions"] == 0 and res["canary_tokens_found"] == 0 \
        and not res["side_channel_hits"]
    print("LEAK SCAN CLEAN" if clean else "LEAK SCAN FOUND LEAKS")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
