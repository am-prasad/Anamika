import { cn } from "@/lib/cn";

/** Quiet shimmer-free placeholder (no infinite motion). */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-[14px] bg-white/[0.05]", className)} aria-hidden />;
}
