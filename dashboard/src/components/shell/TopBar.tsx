"use client";

import { LoaderCircle, Play } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { cn } from "@/lib/cn";
import type { Dataset, Preset } from "@/lib/types";

import { useRun, useSelection } from "./useRun";

const PRESET_LABEL: Record<string, string> = { strict: "Strict", balanced: "Balanced", research: "Research" };
const PRESET_ORDER = ["strict", "balanced", "research"];

/** Dataset picker, policy preset, live status and the one primary action. */
export function TopBar({ datasets, presets, offline }: { datasets: Dataset[]; presets: Preset[]; offline: boolean }) {
  const { dataset, preset } = useSelection();
  const router = useRouter();
  const path = usePathname();
  const { run, start, running } = useRun();

  const go = (k: string, v: string) => {
    const q = new URLSearchParams({ dataset, preset, [k]: v });
    router.push(`${path}?${q}`);
  };

  const status = offline ? "offline" : running ? "running" : run?.core?.status === "failed" ? "failed" : run?.core ? "ready" : "idle";
  const ordered = PRESET_ORDER.filter((p) => presets.some((x) => x.name === p));

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center gap-4 border-b border-hairline bg-ink-950/60 px-8 backdrop-blur-[18px]">
      <label className="flex items-center gap-2">
        <span className="label">Dataset</span>
        <select
          value={dataset}
          onChange={(e) => go("dataset", e.target.value)}
          className="glass-1 h-9 rounded-[12px] px-3 font-mono text-[13px] text-text-hi"
          aria-label="Dataset"
        >
          {(datasets.length ? datasets : [{ name: dataset, files: 0 } as Dataset]).map((d) => (
            <option key={d.name} value={d.name} className="bg-ink-900">
              {d.name}
              {d.files ? ` · ${d.files} files` : ""}
            </option>
          ))}
        </select>
      </label>

      <div className="flex items-center gap-2" role="radiogroup" aria-label="Privacy preset">
        <span className="label">Preset</span>
        <div className="glass-1 flex h-9 items-center rounded-full p-1">
          {ordered.map((p) => (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={preset === p}
              onClick={() => go("preset", p)}
              className={cn(
                "h-7 rounded-full px-3 text-[13px] font-medium transition-colors duration-200",
                preset === p ? "bg-teal-400/15 text-teal-400" : "text-text-mid hover:text-text-hi",
              )}
            >
              {PRESET_LABEL[p] ?? p}
            </button>
          ))}
        </div>
      </div>

      <div className="ml-auto flex items-center gap-5">
        <span className="flex items-center gap-2 text-[13px] text-text-mid" aria-live="polite">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              status === "ready" && "bg-teal-400 animate-live",
              status === "running" && "bg-amber-400 animate-live",
              status === "failed" && "bg-rose-500",
              (status === "idle" || status === "offline") && "bg-text-faint",
            )}
          />
          {status === "ready" && "Live · last run complete"}
          {status === "running" && "Running pipeline"}
          {status === "failed" && "Last run failed"}
          {status === "idle" && "No run yet"}
          {status === "offline" && "Backend offline"}
        </span>
        <button
          type="button"
          onClick={start}
          disabled={running || offline}
          className={cn(
            "flex h-10 items-center gap-2 rounded-[12px] px-4 text-[14px] font-semibold transition-all duration-200",
            "bg-teal-400 text-ink-950 shadow-[0_0_0_1px_rgba(45,212,191,0.4),0_8px_24px_rgba(45,212,191,0.25)] hover:bg-[#5eead4]",
            "disabled:cursor-not-allowed disabled:bg-teal-400/30 disabled:text-ink-950/70 disabled:shadow-none",
          )}
        >
          {running ? <LoaderCircle size={16} className="animate-spin" /> : <Play size={16} strokeWidth={2} />}
          {running ? "Running…" : "Run pipeline"}
        </button>
      </div>
    </header>
  );
}
