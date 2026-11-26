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
