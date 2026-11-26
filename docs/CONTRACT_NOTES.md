# Contract notes

Distilled from the organiser toolkit (`START_HERE.md`, `docs/SPEC.md`, `docs/SCORING.md`,
`docs/ATTACKS.md`, `docs/DATASET.md`, `docs/SANDBOX.md`, `docs/FAQ.md`, `scoring.toml`,
`validate_output.py`, `check_dev.py`, `check_submission.py`). **Where this file and
`CLAUDE.md` disagree, the toolkit wins**; conflicts are listed in §9.

## 1. How we are run

| Item | Contract |
|---|---|
| Entry | `raksha.toml` at repo root, `[submission] name / setup / run` |
| Setup | runs once, network allowed, 30 min, inside a pre-created `.venv` (put first on `PATH`) |
| Run | `run` with `{input}` / `{output}` replaced by absolute shell-quoted paths, **no network** |
| Env | `RAKSHA_SECRET`, `RAKSHA_INPUT`, `RAKSHA_OUTPUT`, `RAKSHA_CPUS`, `OMP_NUM_THREADS`…, `HF_HUB_OFFLINE=1` |
| Limits | 2 pinned CPUs, 4,096 MB peak RSS of the whole process tree (50 ms sampling, killed above), 900 s wall |
| Visibility | repo, read-only input copy, output dir, private `TMPDIR` and `HOME` (both **scanned for PII**) |
| Runs | 3 hidden datasets (one "chaos" / unseen-format); each run twice with the same secret, once with a different secret |

## 2. Output layout

```
{output}/
  sanitized/       mirror of the input tree (same relative paths, same formats, UTF-8, BOM allowed)
  report.json      required
  records.jsonl    required for identity credit
  logs/            optional, scanned
  quarantine/      optional, NOT scanned, NOT part of the release
```

* Same relative path per file. A file name that contains PII is **renamed**, and the new path
  is declared in `report.json` under the file's `input_sha256`.
* CSV stays CSV (same delimiter and header; rename a header only if it contains PII).
  JSON keeps structure and value types (declared *generalisable* paths are exempt from the
  type check). FHIR stays a valid R4 Bundle whose references resolve.
* A file we could not process is **never** copied into `sanitized/`.

## 3. `report.json`

```json
{"schema": "raksha-report/1",
 "files": [{"input_sha256": "…", "output": "sanitized/…", "status": "sanitized"},
           {"input_sha256": "…", "output": null, "status": "quarantined", "reason": "unsupported_format"}],
 "counts": {"files_total", "files_sanitized", "files_quarantined", "records_processed",
            "identifiers_detected", "records_linked", "records_generalized",
            "records_suppressed", "records_quarantined"},
 "entities": {"PATIENT_NAME": 0, "PHONE": 0},
 "timing": {"seconds": 0.0}, "resources": {"peak_rss_mb": 0.0}}
```

* Every input file is listed by SHA-256 of its bytes, never by name. `status` ∈
  `sanitized | quarantined | suppressed`.
* Counts are cross-checked against what was really exported (report-quality honesty =
  `files_total`, `files_sanitized`, `files_quarantined`). The report itself is PII-scanned.
* Duplicate inputs (byte-identical files at two paths) share one SHA; the validator accepts a
  duplicate exported at its own path even if only one `files` entry carries that SHA.

## 4. `records.jsonl`

One object per **patient-bearing** exported record: `{"file", "loc", "patient"}` plus
optional `out` (output locator if it differs) and `status` (`sanitized|generalized|suppressed`).

| Record | `loc` |
|---|---|
| CSV/TSV row | `row:N`, 0-based, header excluded, **input** row index |
| JSON record | RFC 6901 pointer, e.g. `/visits/3`, `/results/12`, `/patients/0` |
| text note, FHIR Bundle, single-object JSON | `doc` |

* The evaluator maps each truth record to the **longest** reported `loc` covering it
  (exact → JSON-pointer ancestor → `doc`).
* `patient` is our pseudonym or `null`. It must **appear inside that exported record**
  (pseudonym-consistency credit; the attacker also only sees in-data pseudonyms).
* `file` paths must point to exported files (validator error otherwise).

## 5. Answer key (`dev/truth/truth.json`) — format

* Top level: `schema, generator_version, seed, profile ("small"), chaos (false), ref_date
  (2026-11-20), files, patients (48), traps, linkability, canaries (4)`.
* `files[<rel path>]`: `path, format (text/json/fhir/csv/tsv/xml/pdf/binary), encoding,
  delimiter, expect (sanitize | either), category, clean, date_hint (dmy|mdy), sha256, size,
  generalizable (e.g. "col:Age", "/patients/[]/dob"), units`.
* `units[<loc>]`: `loc, patient, cid, link (required|none|ambiguous), tags, entities,
  preserve, dates, fields, exclude`. File-level units use `@filename`, `@file` (keys and
  metadata) and `@header`.
* `entities[]`: `type, surface, person, role (patient|relative), script (latin|deva|hinglish),
  channel (content|filename|metadata|key|base64|header), match (name|digits|digits_exact|
  text|dob), key, critical`.
* `preserve[]`: `text, kind, weight, path` — kinds: lab, medication, vital, doctor,
  frequency, lab_test, dose, diagnosis_code, diagnosis, complaint, history, context,
  department, **district**, ward, procedure, package, amount, **hospital**, eponym, range.
* `dates[]`: `true, event, patient, hint, path` (admission, discharge, lab_collected, …).
* `fields[]`: `kind (age|gender|dob|village|district|pin), true, path, patient`.

## 6. Placeholder conventions

The toolkit defines **none**. The scorer only checks that PII keys are absent and that
preserve-probes survive (1.0 at the original field, 0.8 elsewhere in the record). Typed
placeholders (`[PHONE]`, `[ADDRESS]`, …) are therefore our choice. Constraint from
token-retention: placeholders must not eat neighbouring non-PII tokens.

## 7. Scorer behaviour that drives design

**Leak counting.** Per PII mention, keys are: identifying *name tokens* (generic tokens like
Devi, Kumar, Md., ji excluded), *digit cores* of IDs/phones (matched across separators,
Devanagari digits and JSON numbers), *exact text* (email, PAN, ABHA address, insurance ID,
house/locality/landmark/village) and *DOB* (any format resolving to the true date). Both
sides are NFKC-normalised, homoglyph-folded, zero-width-stripped, Indic digits → ASCII,
diacritics stripped, casefolded; base64 / hex / `\uXXXX` / HTML entities / %-encoding are
decoded and appended. A token inside a preserve-probe (e.g. "Dr. Ramesh") is allowed.
Unlocatable records → any occurrence anywhere in the file counts.

**Detection (20).** F2 of contextual precision and recall. Recall = ½ weighted macro over
types + ½ macro over scripts (latin / deva / hinglish) — Devanagari names matter as much as
all Latin entities together. Precision = mean survival over the meaning-trap groups
(doctor, doctor-vs-relative, c/o-complaint, k/c/o, h/o, hospital-ward, dose, 1-0-1, eponym,
asha) + token retention on clean docs.

**Identity (15).** 0.4 pairwise F0.5 + 0.3 B³-F1 + 0.1 language trap + 0.1 fragmented trap +
0.1 homonym separation. No pseudonyms at all ⇒ 0. Link when the data connects records: a
shared strong ID unique to the patient, or same name + a second clue (DOB, relative, village
+ age ±1) unique in the dataset.

**Privacy (25).** `(1 − risk) × min(1, utility / 0.40)`. Risk = weighted A1 direct exposure
0.2, A2/A3 registry linkage 0.2, A4 profile re-id 0.2, A5 targeted 0.2, A6 pseudonym
inversion 0.1, A7 cross-release 0.1; A1–A5 normalised by the same attack on raw input.
A5 recovers a *global* date shift from ≥ 2 confidently re-identified people, and measures
LOS from intervals inside one record (per-patient shifts cannot hide LOS). Rare conditions
weigh ×8 when shared by ≤ 3 profiles.

**Utility (20).** probes 0.35, temporal 0.20 (pairwise intervals exact, LOS), generalisation
0.10 (age exact 1.0 / ≤5y band 0.9 / ≤10 0.8; village kept 1.0 / tehsil 0.8 / district 0.7;
PIN 6-digit 1.0 / true 3-digit prefix 0.7; DOB exact 1.0 / shifted ≤ 1 y 0.9 / year 0.8;
a band excluding the true age scores 0), statistics 0.15 (ICD mix TVD, LOS histogram, lab
medians ±10%), token retention 0.10, record retention 0.10.

**Integrity (10).** format validity 0.15, schema preservation 0.20 (CSV column count, header
names, row count; JSON key-path Jaccard + value types; text line-count ratio), FHIR validity
0.15, pseudonym consistency 0.10, channel hygiene 0.15 (7 channels; leftover temp files
without PII = 0.5), quarantine handling 0.15, report quality 0.10.

**Performance (10).** reliability 0.30 (exit 0), wall time 0.30 (log-linear between
`time_good` and `time_limit`; small 15/300 s, standard 60/900 s), peak memory 0.20
(**512 MB good**, 4,096 MB limit), determinism 0.20, optional scaling 0.15.

**Penalties.** −1 per unique leaked direct identifier / full name (cap −25); −3 per canary
anywhere incl. logs/tmp/stdout (cap −15); −5 per malformed/unsupported PII file copied raw
(cap −20); −10 false success; −5 input tampering. Total not floored at 0.

**Calibration anchors.** reference ≈ 80 (normal) / ≈ 48–50 (chaos); redact-all ≈ 22;
naive regex ≈ 4; passthrough ≈ −19.5. The chaos round costs the reference ~30 points —
that is where generalisation pays.

## 8. Toolkit checkers

* `validate_output.py` — format only: `sanitized/` exists, every input exported at the same
  path or declared by SHA, declared outputs exist, statuses valid, UTF-8, `records.jsonl`
  shape and file references, counts/timing/resources present (warnings).
* `check_dev.py` — rough guide: substring leak test of normalised surfaces per type /
  script / channel, canaries anywhere under `{output}`, preserve-probe survival, pairwise
  linkage on `link=required` units, raw copies of `expect=either` files.
* `check_submission.py --run` — raksha.toml, README ≥ 300 words, a PDF somewhere in the repo
  (not under `dev/`), no LLM packages, policy.yaml, then 3 runs: exit 0, CONTRACT OK, same
  secret → identical `sanitized/` + `records.jsonl`, other secret → different, secret never
  written, input untouched.

## 9. Conflicts with CLAUDE.md (toolkit wins)

| # | CLAUDE.md says | Toolkit says | Resolution |
|---|---|---|---|
| 1 | Facility names → `HOSP-A…` pseudonyms | `hospital`, `department`, `ward`, `district` are **preserve-probes** | Keep hospital, department, ward and district text |
| 2 | k-anon escalation may widen admission month → quarter | Temporal utility needs exact intervals; LOS histogram and lab dates are scored | Never coarsen dates; escalate on age band / location / rare diagnosis only, for rare records only |
| 3 | Peak RSS target < 1.5 GB | Full memory points at **≤ 512 MB** | Target < 300 MB on dev |
| 4 | Runtime target < 3 min | Full time points at ≤ 10–15 s (small) / 60 s (standard) | Target < 10 s on dev |
| 5 | Placeholder tokens `[PHONE]` etc. "follow toolkit if specified" | No convention specified | Keep our typed placeholders |
| 6 | Quarantine reason = class name + stage | Reason is free text, scanned for PII | Use a closed vocabulary (`unsupported_format`, `empty_file`, `undecodable_text`, `json_too_deep`, `malformed_json`, `parse_error.<stage>`) |
| 7 | `records.jsonl` one line per patient record | Spec: per *patient-bearing* record; starter also lists non-patient records | Keep listing every record with `null` when unlinked (harmless; revisit for `clean/`) |
| 8 | Date shift in [−365,−30] ∪ [30,365] | DOB shifted ≤ 1 y still scores 0.9; A7 penalises shifted dates that coincide across secrets | Keep CLAUDE.md range; DOB handled by policy (band or shifted year) in S1 |

## 10. Open questions for the organisers

* Is `records.jsonl` expected to list records of `clean/` documents (no patient)?
* Is a CSV that actually contains JSON (`misc/mislabeled_export.csv`) better sanitised as JSON
  at the same path or quarantined? (`expect = either`, so both are safe.)
