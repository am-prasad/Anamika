# Privacy model

## Threat model

The attacker holds:
- the release (`sanitized/` plus in-data pseudonyms);
- an electoral-roll style registry of the whole population: name, relative, gender, age, house, mohalla, village, tehsil, district, PIN, and sometimes phone, email and last-4 Aadhaar digits;
- gossip-level known facts: a true visit date, the hospital, sometimes the condition;
- public transliteration and gazetteer knowledge.

Following Kerckhoffs' principle, we assume the attacker knows our method. Only
`RAKSHA_SECRET` is secret.

| Attack | What it exploits | Our defence |
|---|---|---|
| A1 direct exposure | surviving names / IDs anywhere | multi-channel detection, safe file names, PII-free side channels |
| A2/A3 registry linkage | age, gender, village, PIN, house, name tokens | 10-year bands, location generalised to state, no PIN, no DOB |
| A4 profile aggregation | pooling a pseudonym's records into one profile | nothing in any record narrows below state + gender + 10-year band |
| A5 targeted (known facts) | visit dates, hospital, rare conditions, global-shift recovery | per-patient secret offsets (no global shift to recover); coarse QIs make many profiles consistent |
| A6 pseudonym inversion | hashes of UHID / phone / name | HMAC-SHA256 under an HKDF sub-key; no ID digits embedded |
| A7 cross-release | stable pseudonyms or shifts across secrets | all keys derived from the per-release secret |

## Measured risk (practice data, `backend/tools/attacker.py`)

`tools/attacker.py` re-implements the published attacks (docs/ATTACKS.md of the kit) and runs
them on the raw input and on our release. A1–A5 are reported relative to raw, as the scorer
does, and `resistance = 1 − weighted risk`.

| Preset | Resistance | A1 | A2/A3 | A4 profile | A5 targeted | A6 | A7 | Medical kept | Token retention |
|---|---|---|---|---|---|---|---|---|---|
| research (tehsil, 5-yr, PIN3, DOB shifted) | 0.627 | 0.02 | 0.28 | 0.91 | 0.65 | 0 | 0 | 100% | 99.7% |
| **balanced (default)** (state, 10-yr, no PIN, DOB removed) | **0.914** | 0.02 | 0.06 | **0.02** | 0.33 | 0 | 0 | 98.1% | 97.4% |
| strict (state, 20-yr, rare conditions → ICD chapter) | 0.917 | 0.02 | 0.04 | 0.02 | 0.33 | 0 | 0 | 97.4% | 97.2% |

Absolute rates under the default: registry linkage 66.7% → 4.1% probability on the true person;
profile re-identification 98% → 2% of patients; targeted attack 82% → 27%; direct exposure
100% → 2%.

## How the default was chosen

Two grids of settings were measured on the same data
([SCORE_LOG](SCORE_LOG.md#s4-privacy-grid)). Findings:

1. **Village, tehsil and PIN were not what identified people.** With village → tehsil, 5-year
   bands and a PIN prefix, pooling a patient's records left exactly one registry candidate for
   25 of 37 identified patients, through district + gender + band + **birth year**.
2. **A shifted DOB still reveals the birth year.** Our shift is under a year and the attacker
   tolerates ±1 year. Removing DOB moved resistance 0.648 → 0.789.
3. **District is the next fingerprint.** With about 30 registry people per district, district +
   gender + band is near-unique. State level moved resistance 0.789 → 0.913 (A4 0.34 → 0.02),
   at a cost of 1.9% of preserve-probes (district probes) and the generalisation credit of
   district fields.
4. **20-year bands add little** (0.913 → 0.917) and cost age precision, so the default stays at 10.
5. **Rare-value suppression did not move this attacker.** A5 is driven by visit dates and
   hospital, not condition text. It costs probes, so it is off by default and on in `strict`.

Estimated net effect of balanced vs research: +7.2 privacy points (25 × Δresistance), for
about 1 utility point (probes, generalisation credit, token retention).

## Quasi-identifiers and their handling (balanced)

| QI | Treatment | Why |
|---|---|---|
| Age | 10-year band containing the true age; 90+ top-coded | truthful, kills exact-age filtering |
| DOB | removed (`[DOB]`; FHIR `birthDate` dropped, optional in R4) | a shifted DOB still leaks the birth year |
| Village / mohalla / house / landmark | removed or generalised to state | the strongest location fingerprints |
| Tehsil, district | generalised to state | registry classes of about 30 people per district are too small |
| PIN | removed | a 3-digit prefix is district-level |
| Dates | per-patient secret shift (±30–365 days) | intervals and LOS exact; no global shift to recover |
| Diagnoses | kept (ICD codes always kept); rare texts → ICD chapter in `strict` | clinical value |
| Hospital, department, ward, doctor | kept | preserve-probes; not patient identifiers |

## Date shift

`offset = ±(min + HMAC(k_shift, pseudonym) mod (max − min + 1))`, with `[30, 365]` days. Every
date of one patient uses the same offset, so every interval is exact. Unlinked records get a
per-record offset. Dates are shifted wherever they occur, including FHIR `meta.lastUpdated` and
export metadata. The attacker's global-shift recovery finds no shared offset in our releases.

## k distribution

`anamika/privacy/kanon.py` reports (age band, gender, region) class sizes. The registry-based
attacker is the stronger test, because what matters is the population a record must hide in,
not the dataset's own patients.

## Limits of the measurement

Our attacker follows the published method; the organisers' code is sealed until results. A5 is
inherently noisy (coincidental date matches across pooled profiles). Hidden registries are
4–5× the patient count, like the practice one, so the per-district class sizes and the
direction of every result should carry over.
