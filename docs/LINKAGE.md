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

## Status after S4

| Evidence | Key | Rule |
|---|---|---|
| hospital ID (UHID / IPD / reg no.) | `mrn:` | exact, strong |
| mobile, Aadhaar, ABHA, e-mail | `ph:`, `aa:`, `abha:`, `em:` | exact, strong |
| canonical name + DOB | `nd:` / `ndx:` (cross-script) | exact |
| cross-script name + village (+ age ±2) | `nv:` | weak: needs a Fellegi–Sunter score ≥ `fs_threshold` |
| cross-script name + relative's name | `nr:` | weak: FS gate |
| first name + relative's first name | `nf:` | fragment: may only **attach** a singleton to the one cluster already carrying the key |

Fellegi–Sunter weights (log2 m/u):

| Field | Agree | Disagree |
|---|---|---|
| name | +6.6 | — |
| village | +4.2 | — |
| relative | +5.4 | — |
| age ±2 | +3.2 | −3.2 |
| gender | +1.0 | −6.6 |
| DOB | +8.6 | −9.0 |

Cannot-link constraints: Aadhaar, ABHA, DOB, gender, plus age ±2 for weak keys.

**Identity graph.** `linkage.json` and `GET /api/v1/jobs/{id}/graph` list exported records,
the evidence *type* of every merge edge, and every pair kept apart, with the conflicting
attribute names (`dob`, `age`, `fs_score`…). There are no values.

Practice: precision 1.00, recall 0.99, F0.5 1.00, 0 false merges. Fuzz ×3: F0.5 0.99, 0 false merges.
