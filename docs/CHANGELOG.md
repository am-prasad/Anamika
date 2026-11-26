# Changelog

## S0 · Recon & scaffold (2026-11-26)

- Contract notes and data inventory from the organiser toolkit; 8 conflicts with the plan resolved in favour of the toolkit.
- Safety layer: whitelisted PII-free logger, content-free crash hooks, HKDF-SHA256 keyring, encrypted self-wiping temp directory.
- Contract-correct two-pass pipeline (starter-equivalent detection), closed-vocabulary quarantine, honest report with accounting check.
- Pseudonym, date-shift and age-band primitives with tests.
- Tools: scorer-style leak scanner, determinism / secret-rotation / hygiene checker, Markdown → PDF renderer.
- 51 unit tests. Baseline: CONTRACT OK, 84.1% PII visible, 100% medical kept, 0.22 s, 29.6 MB.
