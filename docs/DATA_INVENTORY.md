# Practice data inventory (`dev/input`)

Profile `small`, generator 1.0.0, `ref_date` 2026-11-20, not chaos. **200 files, 48 patients,
4 hospitals, 883 scored records, 3,234 PII mentions, ≈ 4,950 preserve-probes, 4 canaries.**
All values below are counts or shapes; no PII is reproduced here.

## 1. Folders

| Folder | Files | Records | PII | Probes | Formats / encodings | Notes |
|---|---:|---:|---:|---:|---|---|
| `registration/` | 5 | 93 | 967 | 95 | CSV utf-8-sig, TSV **utf-16**, CSV **cp1252**, JSON | one byte-identical duplicate `… (1).csv` |
| `opd/` | 30 | 122 | 390 | 2,097 | nested JSON (`_export_meta` + `visits[]`) | PII in `_export_meta.source_path` (metadata channel) |
| `prescriptions/` | 47 | 47 | 141 | 405 | text | Hindi (Devanagari) and English/Hinglish templates |
| `discharge/` | 26 | 50 | 335 | 441 | text | **33 PII in file names** (patient names, IPD numbers) |
| `notes/` | 11 | 21 | 52 | 51 | text | Hinglish nursing notes, visitor log; IPD numbers in file names |
| `lab/` | 40 | 459 | 990 | 1,288 | CSV, JSON, WhatsApp text | **phone numbers in file names**; `bulk_lab_export.json` (144 records) |
| `fhir/` | 19 | 19 | 232 | 319 | FHIR R4 document Bundles | `meta.source`, identifiers, narrative `text.div`, **base64 attachments** |
| `billing/` | 4 | 22 | 88 | 66 | CSV | PAN, insurance / policy IDs, MRNs |
| `clean/` | 4 | 29 | 0 | 67 | CSV, JSON, text | no patient data — must survive untouched |
| `misc/` | 14 | 21 | 39 | 26 | mixed | hidden-leak traps and malformed files (below) |

## 2. Registration schemas (four systems)

| System | Header language | Shape | Date order | Specials |
|---|---|---|---|---|
| Sanjeevani | English | 16 cols: UHID, name, gender, age, DOB, relation, relative, free-text address, village/mohalla, tehsil, district, PIN, mobile, Aadhaar, ABHA, reg date | d/m/Y | address embeds `C/O <relative>`, house no., ward, mohalla, landmark |
| Jeevan Jyoti | **Hinglish transliterated** (`Naam`, `Ling`, `Umar`, `Janm Tithi`, `Pita/Pati ka Naam`, `Pata`, `Gaon`, `Jila`) | 14 cols | d-m-Y | many rows fully in **Devanagari** (`महिला`, `## वर्ष`, Hindi address) |
| Arogya | English legacy | split `LastName` / `FirstName`, `Guardian`, `Street`, `City`, `Zip` | **m/d/Y** | ragged rows, multi-line quoted `Notes`, empty last names |
| DH Hardoi | JSON | `patients[]` with nested `name{first,last,local}`, `guardian`, `contact`, `address`, `ids` | ISO | Aadhaar stored as a **JSON number** under a misspelled key; `name.local` in Devanagari |

## 3. PII by type, script and hiding place

| Type | n | | Script | n | | Channel | n |
|---|---:|---|---|---:|---|---|---:|
| PATIENT_NAME | 962 | | latin | 2,980 | | content | 3,115 |
| MRN | 850 | | deva | 143 | | filename | 48 |
| PHONE | 308 | | hinglish | 111 | | metadata | 40 |
| RELATIVE_NAME | 232 | | | | | key | 12 |
| VILLAGE | 150 | | | | | base64 | 11 |
| HOUSE / PIN | 136 / 136 | | | | | header | 8 |
| DOB | 111 | | | | | | |
| LOCALITY / LANDMARK | 103 / 64 | | | | | | |
| AADHAAR / masked | 71 / 16 | | | | | | |
| ABHA_NUMBER | 46 | | | | | | |
| PAN / INSURANCE_ID | 22 / 22 | | | | | | |
| EMAIL / CANARY | 1 / 4 | | | | | | |

* Devanagari mentions: names 48, relatives 19, villages 33, houses 19, landmarks 8,
  localities 6, **phones 10** (Devanagari digits). Hinglish: names 97 (e.g. `<name> sahab ka
  BP…`, `<name> ji`), relatives 14.
* Hidden channels: file names carry MRN ×34, names ×9, phones ×5; metadata carries names ×20
  and MRNs ×20 (`source_path`, FHIR `meta.source`); JSON keys and one CSV header carry MRN +
  names; base64 carries 9 names, 1 phone and **1 canary**.
* Canaries: 1 in a nursing note, 2 in `misc/` content, 1 in a `misc/` base64 attachment.

## 4. Tricky cases seen

**Meaning traps.** `C/O pain abdomen x 3 days` and `C/O: fever x 3 days` (complaints) vs
`C/O <name>` inside addresses (relative). `K/C/O DM2 x 5 yrs`, `K/C/O addison's disease`,
`H/O …` (history, keep). `Dr. <name> (MD Medicine)`, `Consultant:`, `referred_by`,
`Ref by` (doctor, keep) vs `Attendant: <name>, Mob. …` (relative + phone, remove).
`Paracetamol 650 mg 1-0-1 x 5 days`, `Dolo 650 BD x 5 days`, `0-0-1`, `x 2 wks`,
`Inh Salbutamol 100 mcg 2 puffs` (doses). Eponyms: `Crohn's disease`, `addison's disease`,
`Essential (primary) hypertension`. Wards: `Ward 5 (Medicine)`, `Bed 12` (keep).
Vitals: `BP 117/82`, `SpO2 96%`, `Temp 101.2 F`, `Pulse 88/min`.

**Language traps.** One person as Latin, Devanagari and Hinglish across files; Devanagari
digits in phones; Hindi labels (`नाम:`, `उम्र`, `वर्ष`, `पुत्र/पत्नी`); Hinglish free text
(`<name> ki condition ab stable hai`, `Patient ne raat theek se neend li`).

**Fragmented identity.** `discharge/note_*.txt`: only `<first name>, W/o <husband>` plus a
partial date (`Visit: # September`) — linkable only through name + relative.

**Identifiers.** UHID styles differ per hospital (`SNJ/yy/nnnnnn`, `JJH-nnnnnnn`,
`ASS-nnnnnn`, `DHHnnnn-nnnnnn`), IPD numbers (`IPD-yyyy-nnnnn`, `IP-yy-nnnnn`,
`ADMnnnnnn`, `DHH-IPD-nnnnn`), OPD visit ids, bill numbers, policy numbers, PAN, ABHA
`nn-nnnn-nnnn-nnnn`, Aadhaar spaced or contiguous or as JSON number, phones as
`+91 nnnnn nnnnn`, `+91-nnnnnnnnnn`, `nnnnn-nnnnn`, `0nnnnn-nnnnn`, plain 10 digits.

**Lab.** Per-test rows in CSV (`age_sex` = `48/F`), JSON reports with `patient{name, age,
sex, phone, hospital_uhid}` and `panels[].results[]` (LOINC, value, unit, range), WhatsApp
forwards (`[dd/mm/yy, h:mm pm] <sender>: …`, `Report of <name>  48 Y / F`, `call karo
<phone>`).

**FHIR.** Bundle `type=document` with Composition, Patient (identifier MR + ABHA, name,
telecom, birthDate, address, contact next-of-kin), Practitioner, Encounter, Condition,
MedicationRequest, Observation, DocumentReference with base64 `attachment.data`. Patient
narrative `text.div` repeats name, age, gender and UHID. `meta.source` embeds the UHID.
All internal references are `urn:uuid:` full URLs.

**Malformed / unsupported (`misc/`, `expect = either`).** `deep_export.json` (≈ 1,500-level
nesting, 15 KB), `truncated_opd.json` (cut mid-string, contains a name + mobile),
`hl7_cda_discharge.xml`, `scanned_discharge.pdf`, `photo_rx.jpg`, `empty_export.csv`
(0 bytes), `corrupt_bytes_note.txt` (invalid UTF-8, CRLF), `mislabeled_export.csv` (JSON
inside a `.csv`).

**Hidden-leak traps (`misc/`, must sanitise).** `patient_index.json` (UHIDs as **JSON keys**),
`ward_vitals_sheet.csv` (UHID + name in **CSV headers**, vitals in cells),
`helpdesk_tickets.json` (name + callback number under `meta.raised_by`),
`scanned_consent_form.json` (base64 text attachment with a name and phone),
`ambulance_log.csv` (name + phone inside `remarks`), `README_export.txt` (clean).

## 5. Quasi-identifiers and attacker knowledge

* `fields`: age 552, gender 133, DOB 111, village 126, district 112, PIN 112.
* Dates: lab collected/reported 571, admission 75, discharge 67, registrations 93, OPD and
  prescription visits ≈ 150.
* `dev/attacker/registry.csv`: `rid, name, relation, relative_name, gender, age, house_no,
  mohalla, village, tehsil, district, pin, phone, email, aadhaar_last4` — patients plus
  non-patients.
* `dev/attacker/known_facts.jsonl`: `rid, visit_dates, hospital, condition_hint` (+ decoys).

## 6. Implications for the design

1. Content sniffing must beat extensions (JSON in `.csv`, UTF-16 TSV, cp1252 CSV).
2. Column classification needs Hinglish/Hindi header synonyms **and** value profiling.
3. File names, JSON keys, CSV headers, export metadata and base64 payloads all need the
   same detector as content.
4. Devanagari and Hinglish names are a third of the script-recall average — gazetteer +
   transliteration + context are mandatory, not optional.
5. Doctor lines, hospital names, departments, wards and district names are scored as
   *preserve* — detectors must veto them.
