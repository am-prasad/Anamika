# Changelog

## S0 · Recon & scaffold (2026-11-26)

- Contract notes and data inventory from the organiser toolkit; 8 conflicts with the plan resolved in favour of the toolkit.
- Safety layer: whitelisted PII-free logger, content-free crash hooks, HKDF-SHA256 keyring, encrypted self-wiping temp directory.
- Contract-correct two-pass pipeline (starter-equivalent detection), closed-vocabulary quarantine, honest report with accounting check.
- Pseudonym, date-shift and age-band primitives with tests.
- Tools: scorer-style leak scanner, determinism / secret-rotation / hygiene checker, Markdown → PDF renderer.
- 51 unit tests. Baseline: CONTRACT OK, 84.1% PII visible, 100% medical kept, 0.22 s, 29.6 MB.

## Service layer · FastAPI + uv + Docker (2026-11-26)

- Repository restructured into `backend/` (uv project) and `frontend/` (Next.js placeholder). `raksha.toml` now runs `python backend/main.py`, and the evaluator installs pipeline-only deps exported from `uv.lock`.
- FastAPI service over everything built so far: upload or dataset jobs, status, report, paginated records, file and zip downloads, policy, dataset allow-list. Optional determinism, secret-rotation and leak-scan verification per job.
- Security: hashed API keys, tenant isolation, Redis-backed rate limits, body and upload caps, path-traversal guards, hardening headers, CORS and TrustedHost, PII-free access logs, sandboxed pipeline subprocess, input deletion after run, TTL cleanup.
- Scalability: stateless API replicas, Redis job store and queue, arq workers scalable with `--scale worker=N`, an internal network with no worker egress.
- Docker: one hardened non-root image (API + worker), compose stack with Redis. Verified end to end: the practice dataset gives the same counts as the CLI, 195/195 files deterministic, 1.2 s, 44 MB.
- Tests: 77 (51 pipeline + 26 API).
