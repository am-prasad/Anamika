import { cn } from "@/lib/cn";

import { CountUp } from "./CountUp";
import { GlassCard } from "./GlassCard";

/** Label, big number with count-up, a short qualifier and an optional visual. */
export function KpiTile({ label, value, digits = 0, suffix = "", note, accent = "hi", children, className, delay = 0 }: {
  label: string;
  value: number;
  digits?: number;
  suffix?: string;
  note?: React.ReactNode;
  accent?: "hi" | "teal" | "amber" | "rose";
  children?: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const tone = { hi: "text-text-hi", teal: "text-teal-400", amber: "text-amber-400", rose: "text-rose-300" }[accent];
  return (
    <GlassCard className={cn("flex flex-col gap-3 p-6 animate-rise", className)} style={{ animationDelay: `${delay * 1000}ms` }}>
      <p className="label">{label}</p>
      <p className={cn("font-display text-[48px] leading-none font-[300] tracking-[-0.02em]", tone)}>
        <CountUp value={value} digits={digits} suffix={suffix} delay={delay + 0.15} />
      </p>
      {note && <div className="text-[13px] leading-snug text-text-mid">{note}</div>}
      {children}
    </GlassCard>
  );
}
