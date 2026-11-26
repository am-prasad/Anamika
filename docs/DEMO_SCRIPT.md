# Demo script · Anamika Console (5 minutes)

Run on a production build: `cd dashboard && npm run demo` (builds once, starts FastAPI on :8001 and the console on :3000).
Open `http://localhost:3000` at 1440 × 900 or larger. Dataset **practice**, preset **Balanced**. Press **Run pipeline** once before
the judges arrive; a run takes about a minute including the attack, the reruns and the leak scan.

Measured on the production build: every screen loads in under 0.4 s. A fresh run takes about 60 s; the console shows the
running state and the stepper meanwhile, so never start a run live unless asked.

## 0:00 · Hook (Overview)
> "A 47-year-old woman, a small village, nine days with dengue. With a voter list, can you find her? On the raw records
> an attacker re-identifies 98% of patients. On ours, 2%."

- Point at the **Re-identified** tile (2%, down from 98%), then **Canary leaks 0 of 8** and **0 of 3,230** mentions.
- The figure: amber identity particles leave the body for the shield; the teal figure is what research keeps.
- Stepper: 200 files ingested, 3,399 identifiers, 53 patients, verify 0 leaks. Runtime 2.5 s, 46 MB against 15 min / 4 GB.

## 0:50 · Redaction Studio
- The default note is a Hinglish nursing note. Say: "teal removed, amber generalised, green outline kept."
- Show `BP 109/76`, `650 mg`, `RBS 199 mg/dL` in green: *the meaning trap*. Dates in amber: 15/04 becomes 10/06, the times stay.
- Search `Discharge_Summary_X2TBQH5` and open it: Devanagari discharge summary. `मरीज़ का नाम` becomes the pseudonym,
  `पति का नाम` becomes `[RELATIVE]`, the Devanagari-digit phone becomes `[PHONE]`, `Dr. …` stays.
- Hover any highlight: entity type and the rule that fired. Toggle **Show what we kept** off and on.

## 1:50 · Identity Graph
- "877 records, 53 patients." The cyan patient spans 8 record types: billing, discharge, FHIR, lab, notes, OPD, prescriptions,
  registration. Read the evidence bars: hospital ID, Aadhaar, ABHA.
- Click a card under **Same name, different person**: two records ring up with a dashed refused link. Read the reason:
  "ages disagree beyond the tolerance". "A wrong merge hands one patient's history to another, so a conflict always wins."

## 2:50 · Attack Simulator
- Dumbbells: direct exposure 100% → 2.1%, profile re-identification 97.9% → 2.1%, targeted 82% → 26%.
- "What the attacker got": global date shift recovered **yes → no**. "There is no single shift to undo: every patient has their own."
- Click **Research** in the policy switch: re-identification jumps to 90%, clinical values 100%. Back to **Balanced**.
  The trade-off chart shows the three presets measured, not assumed.

## 3:50 · Clinical Integrity
- 98.1% of 4,763 / 4,855 clinical values kept; length of stay 34 / 34 exact; age bands 359 / 359 truthful.
- The only amber bar is district: "raised to state by policy, on purpose."
- LOS scatter: every admission on the diagonal.

## 4:20 · Security & Audit
- Every channel clean: text, file names, CSV headers, JSON keys, metadata, base64, logs.
- 194 / 194 files byte-identical on rerun; 0 of 53 pseudonyms survive a new secret.
- Quarantine list by SHA-256 only. The key diagram: one secret, HKDF, four keys, nothing stored.

## 4:45 · Close
> "An offline research-data gateway for hospital networks: DPDP- and ABDM-ready, on-prem, no model, no network,
> and it proves its own privacy every run."

## Fallbacks
- Backend down: every screen shows "The Anamika service is not reachable"; restart with `npm run demo`.
- No WebGL on the demo machine: the hero falls back to a static figure automatically.
- Reduced motion on: all numbers render final values, the scan line and the hero animation are skipped.
- Screenshots of every screen are in `docs/stages/s5_screens/` as a last resort.
