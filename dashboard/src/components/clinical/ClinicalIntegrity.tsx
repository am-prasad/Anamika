"use client";

import { Table2 } from "lucide-react";
import { useState } from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

import { GlassCard } from "@/components/ui/GlassCard";
import { fmt, pct } from "@/lib/format";
import type { UtilityResult } from "@/lib/types";

/** Single-series charts use one hue: chart slot 1 (validated on #0A1424). */
const HUE = "#3987E5";
const GEN = "#C98500"; // slot 4: a deliberate generalisation, labelled in text as well

/** Probe kinds the policy generalises on purpose, with the reason shown next to the bar. */
const BY_POLICY: Record<string, string> = {
  district: "raised to state by the location policy",
  tehsil: "raised to state by the location policy",
  pin: "removed by the PIN policy",
};

function label(kind: string) {
  return kind.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function ClinicalIntegrity({ u }: { u: UtilityResult }) {
  const [table, setTable] = useState(false);
  const kinds = Object.entries(u.probes)
    .map(([k, [kept, n]]) => ({ k, kept, n, r: n ? kept / n : 1 }))
    .sort((a, b) => a.r - b.r || b.n - a.n);

  const los = new Map<string, { before: number; after: number; n: number }>();
  for (const p of u.los ?? []) {
    const key = `${p.before}:${p.after}`;
    const cur = los.get(key);
    if (cur) cur.n += 1;
    else los.set(key, { ...p, n: 1 });
  }
  const losPts = [...los.values()];
  const losMax = 2 * Math.ceil((Math.max(5, ...losPts.map((p) => Math.max(p.before, p.after))) + 1) / 2);
  const losTicks = Array.from({ length: losMax / 2 + 1 }, (_, i) => i * 2);
  const losExact = (u.los ?? []).filter((p) => p.before === p.after).length;

  return (
    <div className="grid grid-cols-12 gap-6">
      <GlassCard className="col-span-12 p-6 xl:col-span-7" aria-label="Clinical values kept, by kind">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="label">Clinical values kept, by kind</p>
            <p className="mt-1 text-[13px] text-text-mid">
              Every value a researcher needs, checked one by one against the answer key: {fmt(u.probe_total[0])} of {fmt(u.probe_total[1])}.
            </p>
          </div>
          <button type="button" onClick={() => setTable((t) => !t)} aria-pressed={table} className="flex items-center gap-1.5 rounded-[8px] px-2 py-1 text-[12px] text-text-mid hover:bg-glass-1">
            <Table2 size={14} strokeWidth={1.5} /> {table ? "Chart" : "Table"}
          </button>
        </div>
        {table ? (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="label text-left">
                <th className="pb-2 font-[600]">Kind</th>
                <th className="pb-2 text-right font-[600]">Kept</th>
                <th className="pb-2 text-right font-[600]">Checked</th>
                <th className="pb-2 text-right font-[600]">Share</th>
              </tr>
            </thead>
            <tbody>
              {kinds.map((d) => (
                <tr key={d.k} className="border-t border-hairline">
                  <td className="py-1.5 text-text-hi">{label(d.k)}</td>
                  <td className="num py-1.5 text-right text-text-mid">{fmt(d.kept)}</td>
                  <td className="num py-1.5 text-right text-text-mid">{fmt(d.n)}</td>
                  <td className="num py-1.5 text-right text-text-hi">{pct(d.r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <ul className="grid grid-cols-1 gap-x-8 gap-y-2.5 md:grid-cols-2">
            {kinds.map((d) => {
              const policy = d.r < 1 ? BY_POLICY[d.k] : undefined;
              return (
                <li key={d.k} title={`${label(d.k)}: ${fmt(d.kept)} of ${fmt(d.n)} kept`}>
                  <div className="flex items-baseline justify-between gap-3 text-[13px]">
                    <span className="text-text-hi">{label(d.k)}</span>
                    <span className="num text-text-mid">
                      {fmt(d.kept)}/{fmt(d.n)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-glass-1">
                    <div className="h-full rounded-full" style={{ width: `${Math.max(2, d.r * 100)}%`, background: policy ? GEN : HUE }} />
                  </div>
                  {policy && <p className="mt-1 text-[12px] text-amber-400">{policy}</p>}
                </li>
              );
            })}
          </ul>
        )}
      </GlassCard>

      <GlassCard className="col-span-12 p-6 xl:col-span-5" aria-label="Length of stay before and after">
        <p className="label">Length of stay, before → after</p>
        <p className="mt-1 text-[13px] text-text-mid">
          Each admission&rsquo;s days in hospital, computed from the raw dates and from the shifted ones. {losExact} of {(u.los ?? []).length} sit on the
          diagonal: one offset per patient keeps every interval exact.
        </p>
        <div className="mt-4 h-[300px]">
          {losPts.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 10, right: 16, bottom: 22, left: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                <XAxis type="number" dataKey="before" name="Days, raw" domain={[0, losMax]} ticks={losTicks} allowDecimals={false} tick={{ fill: "#8296AC", fontSize: 12 }} stroke="rgba(255,255,255,0.12)" label={{ value: "Days in hospital, raw", position: "insideBottom", offset: -12, fill: "#8296AC", fontSize: 12 }} />
                <YAxis type="number" dataKey="after" name="Days, release" domain={[0, losMax]} ticks={losTicks} allowDecimals={false} tick={{ fill: "#8296AC", fontSize: 12 }} stroke="rgba(255,255,255,0.12)" width={36} label={{ value: "Release", angle: -90, position: "insideLeft", fill: "#8296AC", fontSize: 12 }} />
                <ZAxis type="number" dataKey="n" range={[60, 260]} name="Admissions" />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: losMax, y: losMax }]} stroke="rgba(232,241,248,0.25)" strokeDasharray="4 4" />
                <Tooltip
                  cursor={{ stroke: "rgba(255,255,255,0.15)" }}
                  contentStyle={{ background: "#102036", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10, color: "#E8F1F8", fontSize: 12 }}
                  itemStyle={{ color: "#E8F1F8" }}
                />
                <Scatter data={losPts} fill={HUE} fillOpacity={0.85} stroke="#0A1424" strokeWidth={2} />
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <p className="pt-16 text-center text-[13px] text-text-lo">This run has no admissions with both dates.</p>
          )}
        </div>
      </GlassCard>
    </div>
  );
}
