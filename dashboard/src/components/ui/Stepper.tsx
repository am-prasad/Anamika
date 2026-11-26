import { cn } from "@/lib/cn";

export interface Step {
  name: string;
  value: string;
  detail: string;
  state: "done" | "active" | "waiting";
}

/** Ingest → Detect → Link → Protect → Verify on a thin ECG baseline. */
export function Stepper({ steps }: { steps: Step[] }) {
  const done = steps.filter((s) => s.state === "done").length;
  // one heartbeat per stage boundary
  const beats = steps
    .map((_, i) => {
      const x = (i + 0.5) * (1000 / steps.length);
      return `L${x - 18},30 L${x - 10},30 L${x - 5},14 L${x + 1},46 L${x + 6},22 L${x + 11},30`;
    })
    .join(" ");
  const progress = done / steps.length;
  return (
    <div className="relative">
      <svg viewBox="0 0 1000 60" preserveAspectRatio="none" className="absolute inset-x-0 top-0 h-[60px] w-full" aria-hidden>
        <path d={`M0,30 ${beats} L1000,30`} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <path
          d={`M0,30 ${beats} L1000,30`}
          fill="none"
          stroke="#2DD4BF"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          pathLength={1}
          strokeDasharray="1"
          strokeDashoffset={1 - progress}
          className="transition-[stroke-dashoffset] duration-[1200ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
          style={{ filter: "drop-shadow(0 0 6px rgba(45,212,191,0.6))" }}
        />
      </svg>
      <ol className="relative grid pt-[68px]" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((s) => (
          <li key={s.name} className="flex flex-col items-center gap-1 px-2 text-center">
            <span
              className={cn(
                "label",
                s.state === "done" && "text-teal-400",
                s.state === "active" && "text-amber-400",
              )}
            >
              {s.name}
            </span>
            <span className="num font-display text-[22px] font-[600] text-text-hi">{s.value}</span>
            <span className="text-[12px] leading-snug text-text-lo">{s.detail}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
