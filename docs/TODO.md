# TODO

## S1 (done)
- [x] Column classifier, hidden channels, text detectors, dates, ages, PIN, village, strong-ID pseudonyms, content sniffing

## S2 (awaiting go-ahead)
- [ ] Fuzz generator + unseen-format runs (0 leaks, no crash)
- [ ] Cross-script name keys for language-trap linking
- [ ] Fragmented-note linking when unique
- [ ] Bench under taskset / memory cap; tag `v1-safe`

## Service layer
- [ ] Policy presets per job (Strict / Balanced / Research) via `ANAMIKA_POLICY`
- [ ] `--debug-spans` export endpoint for the console (S3)
- [ ] Attacker endpoint once `backend/tools/attacker.py` exists (S4)
- [ ] Remind the user about their frontend strategy BEFORE starting the frontend stage

## Later
- [ ] Fuzz generator (unseen schemas, Hindi headers, encodings, broken files)
- [ ] Own attacker (A2–A5) + risk metrics
- [ ] Bench script under `taskset -c 0,1` and memory limit
