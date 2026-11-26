# Detection

## Span model

Every detector emits typed spans `{start, end, type, confidence, rule_id}`. Types:
`PATIENT_NAME, RELATIVE_NAME, PHONE, EMAIL, AADHAAR, AADHAAR_MASKED, ABHA_NUMBER,
ABHA_ADDRESS, PAN, VOTER_ID, MRN, INSURANCE_ID, OTHER_ID, HOUSE, LOCALITY, LANDMARK,
VILLAGE, PIN, DOB, AGE, URL`. `DOCTOR_NAME`, `HOSPITAL`, `WARD` and clinical spans are kept.
They act as vetoes that block overlapping PII spans unless a strong validator fired.

## Layers (stage of arrival)

| Layer | Examples | Stage |
|---|---|---|
| Patterns + validators | phones (+91 / 0 / spaced / Devanagari digits), 12-digit Aadhaar with Verhoeff boost, ABHA `nn-nnnn-nnnn-nnnn`, PAN, email | S0 baseline, S1 full |
| Label context | `Name:`, `नाम:`, `Pt.`, `UHID`, `IPD No`, `Reg No`, `पंजीकरण`, `Mob`, `Attendant` | S1 |
| Column classifier | header synonyms EN / HI / Hinglish (`Naam`, `Gaon`, `Jila`, `Pita/Pati ka Naam`) plus value profiling for unseen headers | S1 |
| Relations and honorifics | `S/o D/o W/o C/O H/o`, `पुत्र पत्नी`, `ji sahab didi bhaiya जी साहब` | S3 |
| Gazetteers + transliteration | Latin + Devanagari given names and surnames, variant collapsing (Mohd / Md. / मोहम्मद) | S3 |
| Propagation | known name tokens of a linked patient masked in all their documents | S3 |
| Meaning-trap resolver | `C/O fever` vs `C/O <name>`, `Dr. X` vs `S/o X`, `650 mg 1-0-1` vs phone, `BP 117/82` vs date | S3 |

## Channels

Content, file names, CSV headers, JSON keys, export metadata (`source_path`, FHIR
`meta.source`), FHIR narrative `text.div`, and base64 attachments (decoded, sanitised,
re-encoded). All of them go through the same detector.

## S0 baseline

Five starter-equivalent regexes (`detect/patterns.py::BASELINE_RULES`) give a reference point
for measuring every improvement. The Verhoeff checksum is implemented and tested, ready for
S1 confidence boosting.

## Status after S3

All layers above are live. Additions since S0:
- **Run-time lexicon** with token-indexed matching.
- **Field classifier reused in text** (`label: value`, `label - value`, `|` segments, `<tag>value</tag>`).
- **Value profiling** for name and address columns, and a pinned **clinical** role.
- Kinship words, `resident of` / `r/o` / `निवासी`, Hinglish particles, the subject of `<name>, W/o <husband>`.
- Voter ID, STD landlines and masked mobiles.

Measured on practice, fuzz and 13 novel templates: 0 leaks, 100% preserve-probes, 99.66% token retention.
