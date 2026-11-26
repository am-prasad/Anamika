/** Number formatting with Indian-English grouping and tabular figures upstream. */
export const fmt = (n: number | undefined | null, digits = 0) =>
  n == null || Number.isNaN(n) ? "—" : n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const pct = (n: number | undefined | null, digits = 1) => (n == null ? "—" : `${fmt(n * 100, digits)}%`);
