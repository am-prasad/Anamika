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

## S1 · Valid end-to-end with real protection (2026-11-26)

- Field classifier for CSV headers and JSON keys (English, Hinglish, Devanagari) with value profiling for unseen headers.
- Indian identifier patterns (phones incl. Devanagari digits, Aadhaar, masked Aadhaar, ABHA number/address, PAN, e-mail, labelled PIN), bounded so doses, frequencies, vitals and lab values never match.
- Run-time lexicon learned from each dataset; context engine for labels, relations, honorifics, Hinglish particles and unseen capitalised names; doctor / facility / tehsil-district vetoes; eponym guard.
- Format-preserving per-patient date shifting, truthful age bands, PIN → 3-digit prefix, village → tehsil.
- Strong-ID linkage with cannot-link constraints; pseudonyms written inside every linked record.
- Hidden channels cleaned: JSON keys, CSV headers, export metadata, FHIR narrative, base64 attachments, file names.
- Practice self-check: 0 / 3,230 PII visible, 0 / 4 canaries, 100% medical values, link F0.5 0.99 (0 false merges), LOS 20/20, 2.6 s, 31 MB. 185 tests.

## S2 · Safe submission frozen (2026-11-26)

- Fuzz generator with answer key: invented names (Latin + Devanagari), renamed headers / keys / labels, re-encodings, DOB formats, hostile files and three novel templates.
- Generalisation fixes found by fuzzing: token-based header rules, value profiling for name and address columns, Devanagari tokens in file names, colon-tolerant context verbs.
- Cross-script phonetic name keys; name + village + age, name + relative and unique-only fragment keys under cannot-link constraints.
- Bench under 2 pinned CPUs and a 4 GB cap: 200 files 2.6 s / 43 MB; 1,245 files 20.4 s / 63 MB.
- Practice: 0 leaks, link F0.5 1.00 (R 0.99), 0 false merges. Fuzz ×3: 0 leaks, F0.5 0.99, 0 false merges. 224 tests. Tagged `v1-safe` locally.


## S3 · Detection & meaning-trap hardening (2026-11-26)

- Utility self-check (preserve-probes by kind, token retention overall and on clean documents).
- 13 novel template shapes in the fuzz set (XML-in-text, ALL-CAPS registers, referral letters, SMS, mixed script, Hinglish labels, headerless CSV, Devanagari headers, JSON `columns` + `rows`, unseen JSON keys).
- Field classifier reused in free text: `label: value`, `label - value`, `|` segments and `<tag>value</tag>`; `resident of` / `r/o` / `निवासी`; kinship words; `मरीज़ <name>`; explicit labels outrank guesses.
- Clinical role pins diagnosis / complaint / drug / test columns; Devanagari category columns never profiled as names; district-level `city` kept.
- Voter ID (EPIC), STD landlines and masked mobiles.
- `--debug-spans DIR`: value-free span / role / rule explanations outside the release.
- Token-indexed lexicon matcher and cached classifiers: 1,245 files 20.4 s → 12.1 s (linear).
- Practice: 0 leaks, 100% probes, 99.66% retention, link F0.5 1.00. Fuzz ×3 and novel templates: 0 leaks. 262 tests.

## S4 · Privacy push and backend completion (2026-11-26)

- `tools/attacker.py`: re-implementation of the published A1–A7 attacks on raw vs release (registry linkage, profile pooling, targeted known facts with global-shift recovery, pseudonym inversion, cross-release).
- Fixed: FHIR `meta.lastUpdated` carried unshifted discharge dates (now shifted everywhere).
- Policy knobs: `location.level` (tehsil | district | state), `ages.dob_policy` (shift | year | remove), `kanon.rare_k` (rare condition / procedure text → ICD chapter; ICD codes kept).
- Presets `research`, `balanced` (default), `strict`, chosen from a measured privacy-utility grid. Default resistance 0.627 → **0.914**; profile re-identification 98% → 2%.
- Linkage: Fellegi–Sunter score gate for weak (name-based) merges; linker records evidence-typed edges and pairs kept apart.
- `--debug-spans` also writes `linkage.json` (identity graph, value-free).
- API: per-job `policy`, `explain`, `utility`, `attack` options; `/explain`, `/graph`, demo-only `/compare` (refused in production), `/policy/presets`; datasets report `has_attacker`.
- Docker end to end: one job with every option on the practice set (resistance 0.916, 0 leaks, 194/194 deterministic).
- Tests: 269.

## S5 · Anamika Console (2026-11-26)

- Next.js 15 console in `dashboard/`: Command Overview with the Dissolving Identity 3D hero, Redaction Studio, Identity Graph,
  Attack Simulator, Clinical Integrity, Security & Audit. Every number from a live FastAPI job; API key server-side only.
- Design system (`docs/DESIGN_SYSTEM.md`): Clinical Glass tokens, offline fonts with Devanagari, validated chart palette,
  reduced-motion and no-WebGL fallbacks, an "Explain this" drawer per screen.
- `npm run demo` starts the API and the console together.
- Fix: relative labels ending in a bare "नाम"/"Name" (`पति का नाम`, `Husband Name`) gave the relative the patient's
  pseudonym; now `[RELATIVE]`. No score regression.
- Fix: the job leak scan treated determinism rerun releases as side channels (47 false hits); now only their logs.
- Production build clean, screens load in under 0.4 s. Tests: 274.


## Submission readiness (2026-11-26)

- Root `main.py` (the organisers' named entry point) hands over to `backend/anamika`; `raksha.toml` runs `python main.py`.
  Output is byte-identical to `python backend/main.py`, from any working directory.
- `Anamika_Project_Brief.pdf`: the 2-page brief (A4, ≥ 10 pt) from `docs/PROJECT_BRIEF.md`, with measured numbers on practice
  and on untuned data. `tools/md2pdf.py --min-pt` enforces the font floor.
- CI (`.github/workflows/ci.yml`): the test suite, plus the organisers' `validate_output.py` and `check_submission.py --run`
  on Python 3.10 and 3.12.
- Verified as the evaluator runs it: fresh clone, fresh venv, `pip install -r requirements.txt`, then `check_submission.py --run`
  gives READY TO SUBMIT. With no network, 2 CPUs and a 4 GB cap: 1.9 s / 39 MB (practice), 2.7 s / 39 MB (unseen set).
- README "Submission at a glance" table.
