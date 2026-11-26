"use client";

import { ArrowLeftRight, Split } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { GlassCard } from "@/components/ui/GlassCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { fmt } from "@/lib/format";
import type { Graph } from "@/lib/types";
import { EVIDENCE_COLOR, EVIDENCE_LABEL, evidenceGroup, prettyEvidence, type EvidenceGroup } from "./evidence";

const GraphCanvas = dynamic(() => import("./GraphCanvas"), { ssr: false, loading: () => <Skeleton className="absolute inset-0" /> });

const CONFLICT: Record<string, string> = {
  age: "ages disagree beyond the tolerance",
  fs_score: "agreement score below the link threshold",
  sex: "sex disagrees",
  dob: "dates of birth disagree",
  strong_id: "different IDs of the same kind",
};

/** Pick the story cluster: the one spanning the most record types and kinds of evidence. */
function storyCluster(g: Graph): string | null {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const kinds = new Map<string, Set<string>>();
  const evidence = new Map<string, Set<string>>();
  for (const n of g.nodes) {
    if (!n.patient) continue;
    if (!kinds.has(n.patient)) kinds.set(n.patient, new Set());
    kinds.get(n.patient)!.add(n.file.replace(/^sanitized\//, "").split("/")[0]);
  }
  for (const e of g.edges) {
    const p = byId.get(e.source)?.patient;
    if (!p) continue;
    if (!evidence.has(p)) evidence.set(p, new Set());
    evidence.get(p)!.add(e.type);
  }
  let best: [string, number] | null = null;
  for (const [p, k] of kinds) {
    const ev = evidence.get(p) ?? new Set();
    const score = k.size * 10 + ev.size * 6 + ([...ev].some((t) => t.includes("cross-script")) ? 15 : 0);
    if (!best || score > best[1] || (score === best[1] && p < best[0])) best = [p, score];
  }
  return best?.[0] ?? null;
}

export function IdentityExplorer({ graph }: { graph: Graph }) {
  const [selected, setSelected] = useState<string | null>(() => storyCluster(graph));
  const [pair, setPair] = useState<[number, number] | null>(null);

  const cluster = useMemo(() => {
    if (!selected) return null;
    const nodes = graph.nodes.filter((n) => n.patient === selected);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter((e) => ids.has(e.source));
    const groups: Record<EvidenceGroup, number> = { id: 0, contact: 0, name: 0 };
    const types = new Map<string, number>();
    for (const e of edges) {
      groups[evidenceGroup(e.type)] += 1;
      types.set(e.type, (types.get(e.type) ?? 0) + 1);
    }
    const files = new Set(nodes.map((n) => n.file));
    const kinds = new Set(nodes.map((n) => n.file.replace(/^sanitized\//, "").split("/")[0]));
    return { nodes, edges, groups, types: [...types.entries()].sort((a, b) => b[1] - a[1]), files: files.size, kinds: [...kinds] };
  }, [graph, selected]);

  // one card per patient pair; several record pairs can be refused between the same two people
  const keptApart = useMemo(() => {
    const m = new Map<string, Graph["kept_apart"][number] & { n: number; reasons: Set<string> }>();
    for (const k of graph.kept_apart) {
      const key = [k.patient_a ?? `r${k.a}`, k.patient_b ?? `r${k.b}`].sort().join("|");
      const cur = m.get(key);
      if (cur) {
        cur.n += 1;
        k.conflict.forEach((c) => cur.reasons.add(c));
      } else m.set(key, { ...k, n: 1, reasons: new Set(k.conflict) });
    }
    return [...m.values()];
  }, [graph]);

  const s = graph.summary;
  const unlinked = s.records - s.linked;

  return (
    <div className="grid grid-cols-12 gap-6">
      <GlassCard className="relative col-span-12 h-[600px] overflow-hidden xl:col-span-8" aria-label="Identity graph of every record">
        <GraphCanvas graph={graph} selected={selected} pair={pair} onSelect={(p) => { setSelected(p); setPair(null); }} />
        <div className="pointer-events-none absolute top-0 left-0 flex w-full items-start justify-between p-5">
          <div className="glass-2 pointer-events-auto rounded-[12px] px-4 py-3">
            <p className="label">Records → patients</p>
            <p className="num mt-1 font-display text-[22px] font-[650] text-text-hi">
              {fmt(s.records)} <span className="text-text-lo">→</span> {fmt(s.patients)}
            </p>
            <p className="mt-0.5 text-[12px] text-text-lo">{fmt(unlinked)} left unlinked on weak evidence</p>
          </div>
        </div>
        <div className="pointer-events-none absolute right-0 bottom-0 p-5">
          <ul className="glass-2 pointer-events-auto space-y-1.5 rounded-[12px] px-4 py-3 text-[12px] text-text-mid" aria-label="Legend">
            {(Object.keys(EVIDENCE_LABEL) as EvidenceGroup[]).map((g) => (
              <li key={g} className="flex items-center gap-2">
                <span className="h-[2px] w-4 rounded-full" style={{ background: EVIDENCE_COLOR[g] }} aria-hidden />
                {EVIDENCE_LABEL[g]}
              </li>
            ))}
            <li className="flex items-center gap-2 pt-1">
              <span className="size-2 rounded-full bg-[#67E8F9]" aria-hidden /> Selected patient
              <span className="ml-2 size-2 rounded-full bg-[rgba(45,212,191,0.55)]" aria-hidden /> Linked
              <span className="ml-2 size-2 rounded-full bg-[rgba(130,150,172,0.55)]" aria-hidden /> Unlinked
            </li>
          </ul>
        </div>
        <p className="pointer-events-none absolute bottom-5 left-5 text-[12px] text-text-lo">Click a dot to open its patient. Scroll to zoom.</p>
      </GlassCard>

      <GlassCard className="col-span-12 flex h-[600px] flex-col overflow-hidden xl:col-span-4" aria-label="Selected patient">
        {cluster && selected ? (
          <>
            <div className="border-b border-hairline p-5">
              <p className="label">One patient, one pseudonym</p>
              <p className="mt-2 font-mono text-[24px] font-medium text-cyan-300">{selected}</p>
              <dl className="mt-4 grid grid-cols-3 gap-3">
                {[
                  ["Records", cluster.nodes.length],
                  ["Files", cluster.files],
                  ["Links", cluster.edges.length],
                ].map(([k, v]) => (
                  <div key={k as string} className="glass-1 rounded-[12px] px-3 py-2">
                    <dt className="label !text-[10px]">{k}</dt>
                    <dd className="num font-display text-[20px] font-[650] text-text-hi">{fmt(v as number)}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-[12.5px] text-text-mid">
                Across {cluster.kinds.length} record types: {cluster.kinds.join(", ")}.
              </p>
            </div>
            <div className="border-b border-hairline p-5">
              <p className="label mb-3">Why these records are one person</p>
              <ul className="space-y-2">
                {cluster.types.slice(0, 6).map(([t, n]) => {
                  const g = evidenceGroup(t);
                  const w = Math.max(6, (n / Math.max(1, cluster.types[0][1])) * 100);
                  return (
                    <li key={t} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-[13px]">
                      <span className="text-text-mid">{prettyEvidence(t)}</span>
                      <span className="num text-text-hi">{fmt(n)}</span>
                      <span className="col-span-2 h-1.5 rounded-full bg-glass-1">
                        <span className="block h-full rounded-full" style={{ width: `${w}%`, background: EVIDENCE_COLOR[g] }} />
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
            <ul className="flex-1 overflow-y-auto p-3" aria-label="Records of this patient">
              {cluster.nodes.slice(0, 60).map((n) => (
                <li key={n.id} className="flex items-center justify-between gap-3 rounded-[10px] px-2 py-1.5 text-[12.5px] hover:bg-glass-1">
                  <span className="truncate font-mono text-text-mid">{n.file.replace(/^sanitized\//, "")}</span>
                  <span className="shrink-0 font-mono text-text-lo">{n.loc}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
            <p className="font-display text-[18px] text-text-hi">Select a patient</p>
            <p className="mt-2 max-w-[32ch] text-[13px] text-text-mid">Click any teal dot to see the records that share its pseudonym and the evidence that joined them.</p>
          </div>
        )}
      </GlassCard>

      <GlassCard className="col-span-12 p-6" aria-label="Records deliberately kept apart">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label flex items-center gap-2 text-text-mid">
              <Split size={14} strokeWidth={1.5} /> Same name, different person
            </p>
            <p className="mt-1.5 max-w-[80ch] text-[14px] text-text-mid">
              These pairs share a name and more, yet the linker refused to merge them. A wrong merge hands one patient&rsquo;s history to
              another, so a conflict or a weak score always wins.
            </p>
          </div>
          <p className="num font-display text-[28px] font-[650] text-text-hi">
            {fmt(s.kept_apart_pairs)} <span className="text-[14px] font-normal text-text-lo">patient pairs kept apart</span>
          </p>
        </div>
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {keptApart.map((k, i) => {
            const active = pair && pair[0] === k.a && pair[1] === k.b;
            return (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => {
                    setPair([k.a, k.b]);
                    setSelected(null);
                  }}
                  aria-pressed={!!active}
                  className={cn(
                    "glass-1 glass-interactive flex w-full flex-col gap-2 rounded-[14px] px-4 py-3 text-left",
                    active && "ring-1 ring-text-hi/50",
                  )}
                >
                  <span className="flex items-center gap-2 font-mono text-[13px] text-text-hi">
                    {k.patient_a ?? "null"} <ArrowLeftRight size={13} className="text-text-lo" /> {k.patient_b ?? "null"}
                    {k.n > 1 && <span className="ml-auto text-[12px] text-text-lo">{k.n} record pairs</span>}
                  </span>
                  <span className="text-[12.5px] text-text-mid">
                    Shared: <span className="text-text-hi">{prettyEvidence(k.shared)}</span>
                  </span>
                  <span className="text-[12.5px] text-text-mid">
                    Kept apart: <span className="text-text-hi">{[...k.reasons].map((c) => CONFLICT[c] ?? c.replaceAll("_", " ")).join("; ")}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </GlassCard>
    </div>
  );
}
