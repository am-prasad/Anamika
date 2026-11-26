# Linkage and pseudonyms

## Principle

Link records only when the data itself connects them. A wrong merge corrupts two patients'
histories and is scored more harshly (pairwise F0.5) than a missed link. When evidence is
weak, the record gets `"patient": null`.

## Evidence per record (S2)

Canonical name key (Devanagari → Latin, honorifics stripped, variants collapsed, tokens
sorted), Indic phonetic key, gender, age / birth-year range, phones, strong IDs (Aadhaar,
ABHA, PAN, UHID / IPD per hospital, insurance), relative name and relation type, village
and PIN, hospital, dates, diagnosis.

## Pipeline

1. **Blocking:** strong ID exact; phone; phonetic key + birth-year window; relative-name key.
2. **Scoring:** Fellegi–Sunter log-likelihood weights per field (agree / partial / disagree).
3. **Clustering with cannot-link constraints:** union only on a shared strong ID, or on a score
   above the threshold with no hard conflict (different strong IDs of the same type,
   incompatible gender or birth year). Every merge is checked against the whole cluster, which
   prevents transitive over-merging, and homonyms stay apart.
4. **Fragmented notes:** `<first name>, W/o <husband>` links only when name, relative and
   hospital/date proximity all agree with exactly one candidate.

## Pseudonyms (implemented in S0)

`PSN-` + 6 Crockford base32 characters of `HMAC-SHA256(k_pseudo, cluster_anchor)`. The anchor
is a deterministic canonical string of the cluster (sorted strong IDs, else sorted member
fingerprints). Collisions are resolved by re-keying with a counter, iterating anchors in sorted
order (`link/pseudonym.py::assign`). The pseudonym is written **inside** every record, in an
existing ID column or the patient line, so the consistency check can verify it.
