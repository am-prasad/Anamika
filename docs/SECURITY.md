# Security design

*Assume the server will be breached one day.* The design limits what a breach of the
machine, the logs or the release can reveal.

## Keys

| Key | Derivation | Used for |
|---|---|---|
| `pseudo` | HKDF-SHA256(secret, salt, "anamika/pseudo") | patient pseudonyms |
| `shift` | … "anamika/shift" | per-patient date offsets |
| `file` | … "anamika/file" | safe output file names |
| `enc` | … "anamika/enc" | AES-256-GCM for spilled intermediates |
| `record` | … "anamika/record" | per-record fallbacks (unlinked records) |

The secret comes only from `RAKSHA_SECRET`. It is not stored on the keyring, never logged
or hashed into output, and `repr(Keyring)` is redacted. Independent sub-keys mean that
learning one derived value gives no leverage over another.

## Side channels

| Channel | Control | Verified by |
|---|---|---|
| stdout / stderr | `SafeLogger` whitelisted templates; argparse errors suppressed; warnings off | `tests/test_safety.py`, `tools/determinism.py` |
| crash output | `sys.excepthook`, `threading.excepthook` print class + stage only | subprocess test with PII in the message |
| `report.json` | SHA-256 per file, closed-vocabulary reasons, counts only | `tools/leak_scan.py` |
| `records.jsonl` | output paths + locators + pseudonyms | `tools/leak_scan.py` |
| output file names | HMAC-renamed when the name holds PII (S1) | `tools/leak_scan.py` (`output_names`) |
| TMPDIR / HOME | nothing written unless spilling; spill encrypted, `0700`, wiped at exit / error / SIGTERM | `tools/determinism.py` (leftover check) |

## Quarantine

Unsupported, empty, undecodable, over-deep or malformed files are never copied. They are
listed by SHA-256 with a reason from a closed vocabulary (`unsupported_format`,
`empty_file`, `undecodable_text`, `binary_content`, `json_too_deep`, `malformed_json`,
`malformed_table`, `file_too_large`, `parse_error.<class>`). We do not write a
`quarantine/` copy: holding raw data there would add risk and earns nothing.

## Input integrity

The input is opened read-only, the output may not sit inside the input tree, and
`tools/determinism.py` re-hashes the input after three runs.
