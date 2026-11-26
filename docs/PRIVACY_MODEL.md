# Privacy model

## Threat model

The attacker holds the release (`sanitized/` plus in-data pseudonyms), an electoral-roll
style registry of the whole population (name, relative, gender, age, house, mohalla,
village, tehsil, district, PIN, sometimes phone, email and last-4 Aadhaar digits), gossip-level
known facts (a true visit date, hospital, sometimes the condition, LOS), and public
transliteration and gazetteer knowledge. Following Kerckhoffs' principle, we assume the
attacker knows our method. Only `RAKSHA_SECRET` is secret.

| Attack | What it exploits | Our defence |
|---|---|---|
| A1 direct exposure | surviving names / IDs anywhere | multi-channel detection, safe file names, PII-free side channels |
| A2/A3 registry linkage | age, gender, village, PIN, house, name tokens | 5-year bands, village/house/locality removed, PIN → 3 digits, district kept |
| A4 profile aggregation | pooling evidence across a pseudonym's records | same generalisation applied to every record; no exact age anywhere in a profile |
| A5 targeted (known facts) | exact visit dates, LOS, rare conditions, global-shift recovery | per-patient secret offsets (no global shift to recover); k-anonymity on rare records |
| A6 pseudonym inversion | hashes of UHID / phone / name | HMAC-SHA256 under an HKDF sub-key; no ID digits embedded |
| A7 cross-release | stable pseudonyms or shifts across secrets | all keys derived from the per-release secret |

## Quasi-identifiers

QI tuple: `(age band, gender, district, diagnosis category)`. Village, house, locality,
landmark and PIN suffix are removed rather than generalised in place. Dates are shifted
per patient, never coarsened, because temporal utility (exact intervals and LOS) is 20% of
the clinical score.

## Date shift

`offset = ±(min + HMAC(k_shift, pseudonym) mod (max − min + 1))`, with
`[min, max] = [30, 365]` days by default. Every date of one patient uses the same offset,
so every interval is exact. Unlinked records get a per-record offset. `shift_multiple_of_7`
can preserve weekdays when a study needs them; by default the weekday is hidden.

## Age bands and DOB

Bands are 5 years wide and always contain the true age at the record's date. Ages of 90 and
over collapse to `90+`. The DOB policy (`shift` by default) applies the patient's offset, which
keeps the generalisation score at 0.9 and stops any format of the true birth date from
appearing.

## k-anonymity escalation (S4)

For each equivalence class smaller than `k` (default 5), we escalate only for the affected
records: widen the age band, then generalise location to district, then suppress the rare
diagnosis text (keeping the ICD chapter where the field allows). Dose, frequency, lab, vital
and LOS fields are never touched.

## Measured risk

S4 adds `tools/attacker.py`, a re-implementation of the published A2–A5 attacks on our own
output and on the raw input. It reports: share of patients uniquely re-identified before and
after, the k distribution, and the targeted-attack success rate. S0 has no measurement yet.
