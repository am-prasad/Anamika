"use client";

import { LoaderCircle, Play } from "lucide-react";

import { useRun } from "./useRun";

/** The primary action, reusable inside empty states. */
export function RunButton({ label = "Run pipeline" }: { label?: string }) {
  const { start, running } = useRun();
  return (
    <button
      type="button"
      onClick={start}
      disabled={running}
      className="mt-2 flex h-11 items-center gap-2 rounded-[12px] bg-teal-400 px-5 text-[14px] font-semibold text-ink-950 shadow-[0_8px_24px_rgba(45,212,191,0.25)] hover:bg-[#5eead4] disabled:bg-teal-400/30"
    >
      {running ? <LoaderCircle size={16} className="animate-spin" /> : <Play size={16} strokeWidth={2} />}
      {running ? "Running…" : label}
    </button>
  );
}
