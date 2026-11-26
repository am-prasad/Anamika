# Decision log (ADR style)

## ADR-001 · Toolkit beats CLAUDE.md on conflicts
**Decision:** keep hospital, department, ward and district text; never coarsen dates.
**Alternatives:** hospital pseudonyms (`HOSP-A`); month→quarter escalation.
**Why:** these are scored preserve-probes and temporal-utility inputs (CONTRACT_NOTES §9).

## ADR-002 · Closed-vocabulary quarantine reasons
**Decision:** reasons come from a fixed set; anything else becomes `parse_error.<class>`.
**Alternatives:** exception messages.
**Why:** messages can embed record content, and `report.json` is PII-scanned.

## ADR-003 · Whitelisted logger instead of a filtering logger
**Decision:** only pre-declared templates with typed fields can be printed.
**Alternatives:** regex-scrubbing free-form logs.
**Why:** a scrubber is only as good as the detector we are still building. A whitelist is safe by construction.

## ADR-004 · HKDF sub-keys from one secret
**Decision:** derive `pseudo`, `shift`, `file`, `enc`, `record` keys with HKDF-SHA256.
**Alternatives:** use `RAKSHA_SECRET` directly as the HMAC key everywhere.
**Why:** domain separation; a derived artefact for one purpose reveals nothing about another.

## ADR-005 · Linear-time JSON depth guard before parsing
**Decision:** count bracket depth outside strings; quarantine above `max_json_depth` (200).
**Alternatives:** raise the recursion limit and parse.
**Why:** a 1,500-deep document would risk a C-stack overflow (a crash, not an exception). Pre-scanning is O(n) and safe.

## ADR-006 · No `quarantine/` copies
**Decision:** quarantined files are reported, never copied anywhere.
**Alternatives:** store them in `output/quarantine/` (allowed, unscanned).
**Why:** zero benefit to the score, and a raw-data copy is exactly what a breach would expose.

## ADR-007 · Measure on a pristine LF copy of the kit
**Decision:** dev measurements use `git archive` of the kit, not the working copy.
**Why:** the working copy on the dev machine has CRLF line endings (172 / 200 files), so SHA-256s and byte content differ from what the evaluator uses.

## ADR-008 · Backend / frontend layout, uv for packages
**Decision:** `backend/` (uv project: the pipeline package `anamika/` plus the FastAPI app `app/`) and `frontend/` (Next.js, later). `raksha.toml`, `config/` and `docs/` stay at the root.
**Alternatives:** keep a flat repo; separate repos.
**Why:** a clean product structure for the console, with no change to what the evaluator runs. `uv.lock` pins everything. The evaluator installs `backend/requirements.txt`, exported from the lock with **pipeline dependencies only** (no FastAPI, Redis or uvicorn).

## ADR-009 · The API runs the pipeline as a subprocess, not in-process
**Decision:** each job executes `python main.py --input … --output …` with a clean env, rlimits and a timeout.
**Alternatives:** import and call `anamika.cli.run` inside the API process.
**Why:** (1) service output is byte-identical to what is scored; (2) a crashing or memory-hungry job cannot take down the API; (3) the per-job secret lives only in the child's environment; (4) workers can be network-isolated.

## ADR-010 · Redis + arq for jobs, rate limits and metadata
**Decision:** Redis holds job records (with TTL), the arq queue and rate-limit counters. An inline queue and memory store cover development and tests.
**Alternatives:** Celery (heavier); a database (overkill for TTL'd job metadata).
**Why:** stateless API replicas, horizontal worker scaling, and one small dependency that fits the async FastAPI stack.

## ADR-011 · Per-tenant, per-release secrets derived from one master secret
**Decision:** `RAKSHA_SECRET = HMAC(master, "anamika/release/v1/" + owner + "/" + release)`.
**Why:** different tenants and releases are unlinkable (the A7 property), and no secret is ever stored or transmitted.

## ADR-012 · Learn a lexicon from each dataset at run time
**Decision:** names, IDs and places classified in structured fields (and from unambiguous text labels) are matched everywhere else in the same run.
**Alternatives:** shipped name gazetteers; a trained NER model.
**Why:** hidden data has new patients, so a shipped list cannot contain them, but every dataset names its patients in registration-style fields. It is offline and model-free, and it generalises by construction.

## ADR-013 · Every JSON file also gets a `doc` record
**Decision:** emit `doc` plus one pointer per collection item. Document-level evidence comes only from parts outside the collections.
**Why:** the evaluator matches truth records to the longest covering locator. A lab report whose `panels[]` list looks like a collection is scored as `doc`, while a multi-patient visits file must not link its patients through the document.

## ADR-014 · Cluster anchor breaks collisions by cluster root
**Decision:** the anchor is the smallest key of the cluster; if two clusters kept apart by a conflict share it, the root record id is appended.
**Why:** otherwise two people separated by a cannot-link constraint would receive the same pseudonym, which is a false merge in the output.

## ADR-015 · Measure generalisation with a fuzz generator that has an answer key
**Decision:** mutate the practice set (names, labels, encodings, templates) and rewrite its truth file consistently, then score with the organisers' `check_dev.py`.
**Alternatives:** hand-written test files; trusting practice-set numbers.
**Why:** the chaos round costs the reference about 30 points. A scored, repeatable unseen-format test turned a hidden 0.25 recall into a visible bug.

## ADR-016 · Weak name evidence only with a second clue, and fragments only attach
**Decision:** cross-script name keys link only together with a village (age ±2) or a relative. First-name + relative keys can only attach singleton records to one already-anchored cluster.
**Why:** the scorer weighs precision twice as much as recall (F0.5). The homonym trap puts same-name people in the data on purpose.

## ADR-017 · One field classifier for headers, keys, text labels and tags
**Decision:** `classify_label` decides roles for CSV headers, JSON keys, `label: value` text and `<tag>value</tag>`.
**Alternatives:** separate label regexes per channel.
**Why:** a synonym learned for one channel immediately protects all of them, which matters most when the chaos round renames labels.

## ADR-018 · Explicit evidence outranks heuristics when spans overlap
**Decision:** when spans overlap, label-based name and place spans decide the type over lexicon and capitalisation guesses. Strong identifiers still outrank both.
**Why:** a correct type gives the right placeholder and evidence (a village stays a village), while redaction coverage is unchanged.

## ADR-019 · Token-indexed lexicon matching
**Decision:** names, IDs and places are matched by tokenising once and looking up sets (multi-word places through a first-word index), instead of compiling growing regex alternations.
**Why:** runtime grew super-linearly with lexicon size; the token index made it linear (exponent ≈ 0.91) and 40% faster on 1,245 files.
