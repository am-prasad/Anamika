import { GlassCard } from "./GlassCard";

/** Shown when no run exists yet or the backend is offline. */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <GlassCard className="flex flex-col items-start gap-3 p-10">
      <p className="label">Nothing to show yet</p>
      <h2 className="font-display text-[28px] font-[600] text-text-hi">{title}</h2>
      <p className="max-w-[56ch] text-[15px] leading-relaxed text-text-mid">{body}</p>
      {action}
    </GlassCard>
  );
}
