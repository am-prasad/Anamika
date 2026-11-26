"""Detection: typed PII spans from patterns, context, gazetteers and column profiles.

Clinical safelists veto overlapping PII spans unless a strong validator fired, which is
how the meaning traps (doses, doctors, eponyms, complaints) are protected.
"""
