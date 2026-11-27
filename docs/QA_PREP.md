# Q&A preparation

Crisp answers to questions judges are likely to ask. Grouped by stage of origin.

## Stage 0: Recon & scaffold

**Q: Why HMAC rather than SHA-256 of the UHID?**
Anyone can hash a list of UHIDs and invert a plain hash, which is exactly attack A6. An HMAC under a
per-release secret cannot be recomputed without the key, and a new secret changes every
pseudonym (A7).

**Q: How do you know no PII reaches your logs?**
Logging is not free-form. Every message is a whitelisted template whose fields are
type-checked: integers, short lowercase identifiers, SHA prefixes. Crash handlers print only
the exception class and the stage. Both are unit-tested with names and phone numbers.

**Q: What happens with a file you cannot parse?**
It is quarantined with a reason from a closed vocabulary, listed by SHA-256 in the report,
and never copied. The run exits 0 only if every input file is accounted for.

**Q: Why not raise the recursion limit for the 1,500-deep JSON?**
Deep recursion in the C JSON decoder can overflow the native stack and kill the process,
and a crash costs reliability points. A linear bracket scan rejects it safely before
parsing.

**Q: Where does the secret go?**
It is read once from the environment and expanded with HKDF into five purpose-specific keys.
The raw value is not stored. It never reaches disk, logs or output, and our determinism tool
checks for it in every output, TMPDIR and HOME.

## Stage 1: Valid end-to-end

**Q: How do you find names that are in no list?**
Three ways, in order. Context: labels, relation markers, honorifics and Hinglish particles. The dataset
itself: any name seen in a structured field is learned and removed everywhere else. A last net:
Title-case phrases that never appear in lower case in this dataset. All 4 canaries were caught.

**Q: How do you keep "Dr. Ramesh" but remove relative "Ramesh"?**
Doctor spans are protected before any name rule runs. Relatives are marked explicitly (`S/o`, `W/o`,
`Attendant`). Eponyms are recognised by use (`'s`, `disease`, `syndrome`), so `Wilson's disease` survives even when a
patient is called Wilson.

**Q: Why shift dates instead of coarsening them?**
Intervals and length of stay are clinical value. One secret offset per patient keeps them exact (20/20
LOS preserved), and the attacker's global-shift recovery learns nothing about anyone else.

**Q: How do you avoid merging two different people?**
Records join only through a shared strong identifier or name + DOB. A merge that would put two Aadhaar
numbers, two DOBs or two genders into one cluster is refused, and a record naming several patients
links nobody. Practice data: 0 false merges.

**Q: Does it work on formats you have not seen?**
The design does not depend on file names or exact headers: synonyms plus value profiling, and a lexicon
learned at run time. It is not yet proven: S2 adds a fuzz generator with renamed headers, new schemas
and encodings, and we will report those numbers.

## Stage 2: Safe submission frozen

**Q: How do you know it works on formats you have never seen?**
We built a generator that replaces every name, renames headers, keys and labels, re-encodes files and
adds new templates, with its own answer key. Before the S2 fixes it showed 0.25 link recall and a 2.2%
leak rate. After them: 0 leaks and 0.97 recall on all three variants, plus 0 of 16 leaks on brand-new templates.

**Q: How do you link a Hindi prescription to an English registration?**
Both names fold to the same phonetic key (Devanagari → ITRANS → spelling-variance folding → consonant
skeleton). A link also needs the same village key and an age within two years, and it never overrides
a conflicting identifier.

**Q: What if a short note matches two patients?**
It keeps its own pseudonym. Fragment keys may only attach to the single cluster that already carries
them; they can never bridge two people.

**Q: Will it fit in 2 CPUs, 4 GB and 15 minutes?**
Measured under `taskset` and a 4 GB `ulimit`: 2.6 s and 43 MB for the practice set, 20 s and 63 MB for a
6× larger set (growth exponent ≈ 1.13).

## Stage 3: Detection hardening

**Q: What if the hidden data uses a label you've never seen?**
Every label our field classifier knows works in every channel: CSV headers, JSON keys, text labels and
XML-like tags. Unknown labels fall back to value shape and the run-time lexicon. Thirteen invented
formats showed 0 leaks.

**Q: How do you prove you don't over-redact?**
We measure what the scorer measures. All 4,855 preserve-probes are kept, 99.66% of non-PII words survive,
and 100% on clean documents. Clinical columns have a pinned role, so a name heuristic can never touch them.

**Q: Will it scale?**
On two pinned CPUs: 2.3 s for 200 files, 12 s for 1,245, under 60 MB. Cost is linear because lexicon
lookups are token set membership, not regex alternations.

**Q: Can judges see why something was redacted?**
Yes. `--debug-spans DIR` writes, per file, the span offsets, entity types and the rule that fired, with no
values and outside the release folder. The demo console reads it.

## Stage 4: Privacy

**Q: How do you know your release resists the attacker?**
We implemented the published attack (registry linkage, profile pooling, targeted known facts with
shift recovery, pseudonym inversion, cross-release) and ran it on raw and released data. Default
resistance is 0.914: profile re-identification drops from 98% to 2% of patients, the targeted attack from 82% to 27%.

**Q: Why remove DOB and generalise to state? Isn't that a lot of utility?**
We measured it. A shifted DOB still gives the birth year, and district + gender + band was near-unique
in a registry of about 30 people per district. Removing both costs 1.9% of preserve-probes and some
generalisation credit (about 1 point) and buys about 7 privacy points. Every dose, lab, vital,
diagnosis code, interval and length of stay is untouched. A `research` preset keeps tehsil and
5-year bands for internal use.

**Q: Why not suppress rare diseases?**
We built it and measured it: it didn't reduce the targeted attack, which is driven by visit dates and
hospital, and it cost clinical value. So it is opt-in (`strict`), limited to diagnosis and procedure
text, and it always keeps the ICD code.

**Q: Can you show why two same-name patients were not merged?**
Yes. The identity graph lists every pair kept apart and the conflicting attribute (`dob`, `age`,
`fs_score`) without values. The console draws it.

## Stage 5 · Console

**Q: Is the console showing real data or a mock-up?**
Real. Every screen reads a live job: press Run pipeline and the numbers come from that run. The browser never sees the
API key; originals are shown only in local demo mode on synthetic data.

**Q: Your first count said 9 wrong merges refused, now 5. Why?**
Nine record pairs were refused on weak evidence. Four of them were later joined by a strong ID, so they are one person
correctly. Five patient pairs stayed apart. We show the honest number.

**Q: What did building the console find?**
Two bugs. A Hindi husband's-name line took the patient's pseudonym, now fixed with tests and no score regression. And
the job leak scan counted ward labels like "Ward 3" inside rerun copies as side-channel hits; reruns are now compared byte
for byte instead.


## Desk review · likely questions

**Q: Do you use any machine-learning model? How many parameters?**
None. Detection is checksummed patterns, a context engine (labels, relation markers, honorifics, Hinglish particles), field
profiling and a run-time lexicon learned from the dataset itself. Linkage is classical record linkage (union-find, phonetic keys,
a Fellegi–Sunter gate). Zero parameters, nothing downloaded, nothing to explain away.

**Q: What is your re-identification risk in one number?**
On our implementation of the published attack: profile re-identification falls from 97.9% of patients on the raw data to 2.1% on
the release; weighted resistance over all six attacks is 0.916. The weakest point is the targeted attack (82% → 26%), because visit
date and hospital still narrow the pool. We say so in the brief.

**Q: How do you know it generalises to the hidden sets?**
We built a generator that replaces every name with invented ones, renames labels and headers, re-renders dates and re-encodes
files. On four such sets: 0 leaks by our scan (1 of 3,291 by the practice checker, a quarantined binary's file name), F0.5 0.99,
0 false merges, 98.1% medical values kept. It also runs byte-identically on Python 3.10 and 3.12.

**Q: What happens if a file is half-readable?**
It is quarantined whole with a reason; we never publish a partially sanitised file. Every input is accounted for in report.json
by SHA-256, and the run exits 0 only if sanitised + quarantined equals the input count.

**Q: What would you build next with a hospital partner?**
An on-prem research-data gateway: the same pipeline behind the FastAPI service, a policy per data-sharing agreement, and the
attack and utility report attached to every release as evidence for DPDP and ABDM reviews.
