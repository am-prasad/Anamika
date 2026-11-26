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
