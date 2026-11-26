# TODO

## S1 (done)
- [x] Column classifier, hidden channels, text detectors, dates, ages, PIN, village, strong-ID pseudonyms, content sniffing

## S2 (done)
- [x] Fuzz generator + unseen-format runs, cross-script linkage, fragment linkage, bench, tag `v1-safe`

## S3 (awaiting go-ahead)
- [ ] 10+ novel template shapes in the fuzz set
- [ ] Precision audit on clean docs and meaning-trap probes under fuzz
- [ ] `--debug-spans` export for the console
- [ ] Token-indexed lexicon matcher (growth exponent ≤ 1.1)

## Service layer
- [ ] Policy presets per job (Strict / Balanced / Research) via `ANAMIKA_POLICY`
- [ ] `--debug-spans` export endpoint for the console (S3)
- [ ] Attacker endpoint once `backend/tools/attacker.py` exists (S4)
- [ ] Remind the user about their frontend strategy BEFORE starting the frontend stage

## Later
- [ ] Fuzz generator (unseen schemas, Hindi headers, encodings, broken files)
- [ ] Own attacker (A2–A5) + risk metrics
- [ ] Bench script under `taskset -c 0,1` and memory limit
