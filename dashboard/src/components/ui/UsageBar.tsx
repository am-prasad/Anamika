/** Value against a hard limit, e.g. runtime vs the 900 s budget. */
export function UsageBar({ value, limit, unit }: { value: number; limit: number; unit: string }) {
  const frac = Math.max(0.012, Math.min(1, value / limit));
  return (
    <div className="mt-1">
      <div className="h-[6px] overflow-hidden rounded-full bg-white/[0.06]" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={limit} aria-label={`${value} of ${limit} ${unit}`}>
        <div className="h-full rounded-full bg-teal-400" style={{ width: `${frac * 100}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-[12px] text-text-lo">
        <span className="num">0</span>
        <span className="num">limit {limit.toLocaleString("en-IN")} {unit}</span>
      </div>
    </div>
  );
}
