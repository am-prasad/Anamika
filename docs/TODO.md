# TODO

## S1 (awaiting go-ahead)
- [ ] Column classifier: header synonyms EN/HI/Hinglish + value profiling
- [ ] Hidden channels: file-name rename, JSON keys, CSV headers, metadata, base64
- [ ] Text detectors: label context, Indian ID patterns, Devanagari digits, dose/vital/doctor vetoes
- [ ] Dates: parse all formats, per-record shift, re-render in original format
- [ ] Ages → bands, DOB shift, PIN → 3 digits, village/house/locality removal
- [ ] Strong-ID pseudonyms written inside records (pulled forward from S2)
- [ ] Quarantine corrupt text; content-sniff JSON in `.csv`

## Later
- [ ] Fuzz generator (unseen schemas, Hindi headers, encodings, broken files)
- [ ] Own attacker (A2–A5) + risk metrics
- [ ] Bench script under `taskset -c 0,1` and memory limit
