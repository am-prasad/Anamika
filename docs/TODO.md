# TODO

## S1 (done)
- [x] Column classifier, hidden channels, text detectors, dates, ages, PIN, village, strong-ID pseudonyms, content sniffing

## S2 (done)
- [x] Fuzz generator + unseen-format runs, cross-script linkage, fragment linkage, bench, tag `v1-safe`

## S3 (done)
- [x] 13 novel templates, utility audit, `--debug-spans`, token-indexed matcher

## S4 (done)
- [x] Own attacker (A1–A7) on raw vs release
- [x] Location level / DOB policy / rare-value suppression (measured)
- [x] Policy presets + privacy-utility grid
- [x] Fellegi–Sunter gate for weak pairs
- [x] API: explain, graph, compare (demo), presets, utility / attack verification

## S5 (console, done)
- [x] Six-screen Next.js console on live runs, demo script, stage report

## S6 (docs, brief & pitch)
- [ ] Two-page brief PDF from the toolkit template
- [ ] Architecture diagram for README, brief and pitch
- [ ] Backup screen recording of the demo
- [ ] QA_PREP to 30 questions
- [ ] Measure hero FPS on a GPU machine

## Service layer (done in S4)
- [x] Policy presets per job, explain / graph endpoints, attack / utility verification
- [x] Remind the user about their frontend strategy BEFORE starting the frontend stage (tracked in S5)

## Later
- [ ] Optional: CRF name model trained on fuzz data (only if it beats the rule engine on held-out fuzz)
- [ ] Optional: attacker speed-up (currently ~2 min per raw-vs-release run)
