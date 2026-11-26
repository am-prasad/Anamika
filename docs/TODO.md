# TODO

## S1 (done)
- [x] Column classifier, hidden channels, text detectors, dates, ages, PIN, village, strong-ID pseudonyms, content sniffing

## S2 (done)
- [x] Fuzz generator + unseen-format runs, cross-script linkage, fragment linkage, bench, tag `v1-safe`

## S3 (done)
- [x] 13 novel templates, utility audit, `--debug-spans`, token-indexed matcher

## S4 (awaiting go-ahead)
- [ ] Own attacker (A2–A5) on raw vs release
- [ ] k-anonymity escalation for rare records
- [ ] Policy presets + privacy-utility curve
- [ ] Fellegi–Sunter scoring for weak pairs

## Service layer
- [ ] Policy presets per job (Strict / Balanced / Research) via `ANAMIKA_POLICY`
- [ ] `--debug-spans` export endpoint for the console (S3)
- [ ] Attacker endpoint once `backend/tools/attacker.py` exists (S4)
- [ ] Remind the user about their frontend strategy BEFORE starting the frontend stage

## Later
- [ ] Fuzz generator (unseen schemas, Hindi headers, encodings, broken files)
- [ ] Own attacker (A2–A5) + risk metrics
- [ ] Bench script under `taskset -c 0,1` and memory limit
