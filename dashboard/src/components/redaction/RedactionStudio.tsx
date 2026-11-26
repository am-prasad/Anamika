"use client";

import { Search } from "lucide-react";
import { motion } from "motion/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { GlassCard } from "@/components/ui/GlassCard";
import { StatusPill } from "@/components/ui/StatusPill";
import { cn } from "@/lib/cn";
import { languages, originalSegments, sanitizedSegments, typeCounts, type Segment } from "@/lib/highlight";
import type { CompareDoc, ReleaseFile } from "@/lib/types";

const MAX_CHARS = 14000;

function Seg({ s }: { s: Segment }) {
  if (s.kind === "plain") return <>{s.text}</>;
  const cls = {
    removed: "bg-teal-400/12 text-teal-400 ring-1 ring-teal-400/25",
    generalized: "bg-amber-400/12 text-amber-400 ring-1 ring-amber-400/25",
    kept: "bg-transparent text-mint-300 ring-1 ring-mint-300/40",
  }[s.kind];
  return (
    <mark title={s.label} className={cn("rounded-[4px] px-[2px] py-[1px] [box-decoration-break:clone]", cls)}>
      {s.text}
    </mark>
  );
}

function Pane({ title, children, className }: { title: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col", className)}>
      <div className="flex h-11 items-center justify-between border-b border-hairline px-5">{title}</div>
      {children}
    </div>
  );
}

/** Original vs Anamika for one file, with the scan reveal and the "kept" toggle. */
export function RedactionStudio({ files, doc, selected, jobId }: { files: ReleaseFile[]; doc: CompareDoc | null; selected: string; jobId: string }) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const [query, setQuery] = useState("");
  const [showKept, setShowKept] = useState(true);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const original = (doc?.original ?? "").slice(0, MAX_CHARS);
  const sanitized = (doc?.sanitized ?? "").slice(0, MAX_CHARS);
  const spans = useMemo(() => (doc?.explain?.spans ?? []).filter((s) => s.end <= original.length), [doc, original.length]);
  const kept = useMemo(() => (doc?.explain?.kept ?? []).filter((s) => s.end <= original.length), [doc, original.length]);
  const dates = useMemo(() => (doc?.explain?.dates ?? []).filter((s) => s.end <= original.length), [doc, original.length]);
  const origSegs = useMemo(() => originalSegments(original, spans, kept, showKept, dates), [original, spans, kept, showKept, dates]);
  const sanSegs = useMemo(() => sanitizedSegments(sanitized, showKept, dates.length > 0), [sanitized, showKept, dates.length]);
  const langs = useMemo(() => languages(original), [original]);
  const counts = useMemo(() => typeCounts(spans), [spans]);
  const structured = doc?.explain && doc.explain.format !== "text";

  const filtered = files.filter((f) => f.path.toLowerCase().includes(query.toLowerCase())).slice(0, 400);
  const open = (p: string) => {
    const q = new URLSearchParams(params.toString());
    q.set("doc", p);
    router.push(`${path}?${q}`, { scroll: false });
  };

  return (
    <div className="grid grid-cols-12 gap-6">
      <GlassCard className="col-span-12 flex h-[640px] flex-col overflow-hidden lg:col-span-3" aria-label="Release files">
        <div className="border-b border-hairline p-4">
          <label className="glass-1 flex h-9 items-center gap-2 rounded-[12px] px-3">
            <Search size={15} strokeWidth={1.5} className="text-text-lo" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${files.length} files`}
              className="w-full bg-transparent text-[13px] text-text-hi placeholder:text-text-lo focus:outline-none"
              aria-label="Search files"
            />
          </label>
        </div>
        <ul className="flex-1 overflow-y-auto p-2" aria-label="Files">
          {filtered.map((f) => {
            const active = f.path === selected;
            const [folder, ...rest] = f.path.split("/");
            return (
              <li key={f.path}>
                <button
                  type="button"
                  onClick={() => open(f.path)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex w-full flex-col items-start rounded-[10px] px-3 py-2 text-left transition-colors",
                    active ? "bg-teal-400/10 text-text-hi ring-1 ring-teal-400/30" : "text-text-mid hover:bg-glass-1 hover:text-text-hi",
                  )}
                >
                  <span className="label !text-[10px]">{folder}</span>
                  <span className="w-full truncate font-mono text-[12.5px]">{rest.join("/") || folder}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </GlassCard>

      <div className="col-span-12 flex flex-col gap-4 lg:col-span-9">
        <GlassCard className="flex items-center gap-3 px-5 py-3">
          <span className="min-w-0 truncate font-mono text-[13px] text-text-hi">{selected}</span>
          <span className="flex gap-1.5">
            {langs.map((l) => (
              <span key={l} lang={l === "हिंदी" ? "hi" : undefined} className="glass-1 rounded-full px-2.5 py-0.5 text-[12px] text-cyan-300">
                {l}
              </span>
            ))}
          </span>
          <span className="ml-auto hidden items-center gap-2 xl:flex">
            {counts.slice(0, 3).map(([t, n]) => (
              <StatusPill key={t} kind="protected" className="whitespace-nowrap">
                {t.toLowerCase().replaceAll("_", " ")} <span className="num text-text-hi">{n}</span>
              </StatusPill>
            ))}
          </span>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap text-[13px] text-text-mid">
            <input type="checkbox" checked={showKept} onChange={(e) => setShowKept(e.target.checked)} className="accent-[#86EFAC]" />
            Show what we kept
          </label>
        </GlassCard>

        <GlassCard className="grid h-[574px] grid-cols-2 overflow-hidden" aria-label="Document comparison">
          <Pane
            className="border-r border-hairline"
            title={
              <>
                <span className="label">Original</span>
                <span className="text-[12px] text-text-lo">synthetic demo data</span>
              </>
            }
          >
            <pre className="flex-1 overflow-auto px-5 py-4 font-mono text-[13px] leading-[1.75] break-words whitespace-pre-wrap text-text-mid">
              {origSegs.map((s, i) => (
                <Seg key={i} s={s} />
              ))}
            </pre>
          </Pane>
          <Pane
            title={
              <>
                <span className="label text-teal-400">Anamika</span>
                <span className="text-[12px] text-text-lo">{structured ? "format preserved" : "line structure preserved"}</span>
              </>
            }
          >
            <div className="relative flex-1 overflow-auto">
              <pre className="px-5 py-4 font-mono text-[13px] leading-[1.75] break-words whitespace-pre-wrap text-text-hi">
                {sanSegs.map((s, i) => (
                  <Seg key={i} s={s} />
                ))}
              </pre>
              {mounted && (
                <motion.div
                  key={`${jobId}:${selected}`}
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 top-0 motion-reduce:hidden"
                  initial={{ height: "100%" }}
                  animate={{ height: "0%" }}
                  transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                  style={{ transformOrigin: "bottom" }}
                >
                  <div className="h-full bg-ink-900/92 backdrop-blur-[1px]" />
                </motion.div>
              )}
              {mounted && (
                <motion.div
                  key={`line:${jobId}:${selected}`}
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 h-px motion-reduce:hidden bg-teal-400 shadow-[0_0_16px_2px_rgba(45,212,191,0.6)]"
                  initial={{ top: "0%", opacity: 1 }}
                  animate={{ top: "100%", opacity: 0 }}
                  transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                />
              )}
            </div>
          </Pane>
        </GlassCard>
      </div>
    </div>
  );
}
