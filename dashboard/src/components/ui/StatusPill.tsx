import { CircleAlert, Check, Eye, ShieldCheck, SlidersHorizontal } from "lucide-react";

import { cn } from "@/lib/cn";

const KINDS = {
  protected: { cls: "text-teal-400 bg-teal-400/10 border-teal-400/25", Icon: ShieldCheck },
  generalized: { cls: "text-amber-400 bg-amber-400/10 border-amber-400/25", Icon: SlidersHorizontal },
  kept: { cls: "text-mint-300 bg-mint-300/10 border-mint-300/25", Icon: Check },
  leak: { cls: "text-rose-300 bg-rose-500/10 border-rose-500/30", Icon: CircleAlert },
  info: { cls: "text-cyan-300 bg-cyan-300/10 border-cyan-300/20", Icon: Eye },
} as const;

/** Status always carries an icon and a word, never colour alone. */
export function StatusPill({ kind, children, className }: { kind: keyof typeof KINDS; children: React.ReactNode; className?: string }) {
  const { cls, Icon } = KINDS[kind];
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium", cls, className)}>
      <Icon size={13} strokeWidth={1.75} aria-hidden />
      {children}
    </span>
  );
}
