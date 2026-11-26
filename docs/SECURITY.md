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
| stdout / stderr | `SafeLogger` whitelisted templates; argparse errors suppressed; warnings off | `backend/tests/test_safety.py`, `backend/tools/determinism.py` |
| crash output | `sys.excepthook`, `threading.excepthook` print class + stage only | subprocess test with PII in the message |
| `report.json` | SHA-256 per file, closed-vocabulary reasons, counts only | `backend/tools/leak_scan.py` |
| `records.jsonl` | output paths + locators + pseudonyms | `backend/tools/leak_scan.py` |
| output file names | HMAC-renamed when the name holds PII (S1) | `backend/tools/leak_scan.py` (`output_names`) |
| TMPDIR / HOME | nothing written unless spilling; spill encrypted, `0700`, wiped at exit / error / SIGTERM | `backend/tools/determinism.py` (leftover check) |

## Quarantine

Unsupported, empty, undecodable, over-deep or malformed files are never copied. They are
listed by SHA-256 with a reason from a closed vocabulary (`unsupported_format`,
`empty_file`, `undecodable_text`, `binary_content`, `json_too_deep`, `malformed_json`,
`malformed_table`, `file_too_large`, `parse_error.<class>`). We do not write a
`quarantine/` copy: holding raw data there would add risk and earns nothing.

## Input integrity

The input is opened read-only, the output may not sit inside the input tree, and
`backend/tools/determinism.py` re-hashes the input after three runs.

## Service-layer data exposure (S4)

- **Explanations** (`--debug-spans`, `/explain`, `/graph`) carry offsets, types, rule ids, sanitised paths and pseudonyms, never values. They are written outside `{output}` and named by SHA prefix.
- **Originals** are served only by `/compare`, only for server-side datasets, only with `ANAMIKA_ALLOW_ORIGINALS=true`. The service refuses to start with that flag in production.
- **Attack and utility verification** read the answer key and registry of demo datasets inside the worker and return rates and counts only.
