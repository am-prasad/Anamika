# Score log

All runs use `RAKSHA_SECRET=practice` on the practice data (pristine LF copy of the kit).
`check_dev` is the organisers' rough self-check; "leak scan" is our scorer-style scanner.
The official score is estimated only from the kit's stated starter level.

| When (UTC) | Stage | Change | PII visible (check_dev) | latin / deva / hinglish | Canaries | Medical kept | Link F0.5 | Leak scan mentions | Side-channel hits | Contract | Runtime / RSS | Est. official |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-26 | S0 | organiser starter (reference) | 84.1% (2,718) | 82.8 / 100 / 100% | 4/4 | 100% | 0.00 | n/a | n/a | OK | n/a | ≈ 8 |
| 2026-11-26 | S0 | Anamika starter-equivalent pipeline | 84.1% (2,717) | 82.8 / 100 / 100% | 4/4 | 100% (4,855) | 0.00 | 84.9% (2,741 / 3,230) | 96 | OK | 0.22 s / 29.6 MB | ≈ 8 |
| 2026-11-26 | S1 | column classifier, patterns, run-time lexicon, context engine | 4.7% (152) | 5.1 / 0 / 0% | 0/4 | 99.8% | 0.97 | n/a | n/a | OK | 3.3 s | n/a |
| 2026-11-26 | S1 | safe-vocab fix, Hinglish particles, name expansion, eponym guard, file-name growth | 0.0% (0) | 0 / 0 / 0% | 0/4 | 100% (4,855) | 0.97 | 0.0% (0 / 3,230) | 0 | OK | 2.6 s / 31 MB | n/a |
| 2026-11-26 | S1 | JSON doc records + call-line phones as evidence | 0.0% (0) | 0 / 0 / 0% | 0/4 | 100% | **0.99** (P 1.00 R 0.96) | 0.0% | 0 | OK + READY (no warnings) | 2.6 s / 31.3 MB | not estimated until S4 attacker |
| 2026-11-26 | S2 | **fuzz 7/8/9 baseline** (unseen names, headers, labels, encodings) | 2.2% (70) | 2.0 / 7.6 / 0% | 0/4 | 100% | 0.63 (R 0.25) | 4.7% | 0 | OK | 2.6 s | — |
| 2026-11-26 | S2 | token header rules, name/address profiling, deva file names | fuzz 0.0% | 0 / 0 / 0% | 0/4 | 100% | fuzz 0.99 (R 0.96) | fuzz 0.0% | 0 | OK | 2.6 s | — |
| 2026-11-26 | S2 | cross-script keys, name+village+age, unique-only fragment keys | dev 0.0% · fuzz 0.0% | 0 / 0 / 0% | 0/4 | 100% | **dev 1.00 (R 0.99) · fuzz 0.99 (R 0.97)** | 0.0% | 0 | OK + READY | 2.6 s / 43 MB (bench); 1,245 files 20.4 s / 63 MB | — |
| 2026-11-26 | S3 | utility tool (token retention), district `city` kept | 0.0% | 0 / 0 / 0% | 0/4 | 100% · retention 99.66% · clean 100% | 1.00 (R 0.99) | 0.0% | 0 | OK | 2.6 s | — |
| 2026-11-26 | S3 | 13 novel templates; label/tag classifier in text, kinship, resident-of, clinical role, JSON tables, voter/landline/masked phone | dev 0.0% · fuzz 0.0% · novel 0 leaks | 0 / 0 / 0% | 0/4 | 100% · 99.66% | dev 1.00 · fuzz 0.99 | 0.0% | 0 | OK + READY | 2.3 s / 41 MB; 1,245 files 12.1 s / 58 MB | — |
