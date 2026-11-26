"use client";

import { LoaderCircle, RotateCcw, Table2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";

import { GlassCard } from "@/components/ui/GlassCard";
import { KpiTile } from "@/components/ui/KpiTile";
import { StatusPill } from "@/components/ui/StatusPill";
import { cn } from "@/lib/cn";
import { pct } from "@/lib/format";
import type { AttackResult, Preset } from "@/lib/types";

/** Raw = series-2 (orange), release = series-1 (blue): validated pair on #0A1424. */
const RAW = "#D95926";
const REL = "#3987E5";

const ATTACKS: { key: string; name: string; what: string }[] = [
  { key: "A1", name: "Direct exposure", what: "A surviving ID or full name anywhere in the release" },
  { key: "A23", name: "Registry linkage", what: "Probability mass the voter-list attacker puts on the true person" },
  { key: "A4", name: "Profile re-identification", what: "Records pooled into profiles, matched with ≥ 50% confidence" },
  {
    key: "A5",
    name: "Targeted attack",
    what: "Known visit date, hospital and rare condition, after trying to undo the date shift",
  },
];

export type PresetAttack = { preset: string; status: string; result: AttackResult | null };

function Dumbbell({ raw, rel }: { raw: number; rel: number }) {
  const lo = Math.min(raw, rel) * 100;
  const hi = Math.max(raw, rel) * 100;
  return (
    <div className="relative h-6" aria-hidden>
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-hairline" />
      <div
        className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-white/20"
        style={{ left: `${lo}%`, width: `${hi - lo}%` }}
      />
      <span
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-ink-900"
        style={{ left: `${raw * 100}%`, background: RAW }}
      />
      <span
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-ink-900"
        style={{ left: `${rel * 100}%`, background: REL }}
      />
    </div>
  );
}

export function AttackSimulator({
  dataset,
  initial,
  attacks,
  presets,
}: {
  dataset: string;
  initial: string;
  attacks: PresetAttack[];
  presets: Preset[];
}) {
  const router = useRouter();
  const [preset, setPreset] = useState(initial);
  const [table, setTable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const cur = attacks.find((a) => a.preset === preset);
  const r = cur?.result ?? null;

  const rerun = async () => {
    setBusy(true);
    setFailed(false);
    try {
      const res = await fetch("/api/attack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset, preset }),
      });
      if (!res.ok) throw new Error("start");
      for (let i = 0; i < 120; i++) {
        await new Promise((ok) => setTimeout(ok, 2000));
        const all = (await (await fetch(`/api/attack?dataset=${encodeURIComponent(dataset)}`)).json()) as Record<
          string,
          { status: string }
        >;
        const st = all[preset]?.status;
        if (st === "succeeded" || st === "failed") break;
      }
      router.refresh();
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  const points = presets
    .map((p) => {
      const a = attacks.find((x) => x.preset === p.name)?.result;
      return {
        name: p.name[0].toUpperCase() + p.name.slice(1),
        key: p.name,
        kept: +(100 * (p.measured.medical_values_kept ?? 0)).toFixed(1),
        resistance: +(a ? a.resistance : (p.measured.resistance ?? 0)).toFixed(3),
      };
    })
    .filter((p) => p.kept > 0);

  return (
    <div className="grid grid-cols-12 gap-6">
      <GlassCard className="col-span-12 flex flex-wrap items-center gap-4 px-5 py-3">
        <span className="label">Policy</span>
        <div role="radiogroup" aria-label="Policy preset" className="glass-1 flex rounded-[12px] p-1">
          {attacks.map((a) => (
            <button
              key={a.preset}
              role="radio"
              aria-checked={a.preset === preset}
              onClick={() => setPreset(a.preset)}
              className={cn(
                "rounded-[9px] px-3 py-1 text-[13px] capitalize transition-colors",
                a.preset === preset ? "bg-teal-400/15 text-teal-400" : "text-text-mid hover:text-text-hi",
              )}
            >
              {a.preset}
            </button>
          ))}
        </div>
        <span className="text-[13px] text-text-mid">{presets.find((p) => p.name === preset)?.description}</span>
        <button
          type="button"
          onClick={rerun}
          disabled={busy}
          className="glass-1 glass-interactive ml-auto flex items-center gap-2 rounded-[12px] px-3.5 py-2 text-[13px] text-text-hi disabled:opacity-60"
        >
          {busy ? <LoaderCircle size={15} className="animate-spin" /> : <RotateCcw size={15} strokeWidth={1.5} />}
          {busy ? "Attacking the release" : "Run the attack again"}
        </button>
        {failed && <StatusPill kind="leak">Could not start the attack</StatusPill>}
      </GlassCard>

      {!r ? (
        <GlassCard className="col-span-12 p-10 text-center text-text-mid">
          {cur?.status === "queued" || cur?.status === "running"
            ? "The attacker is working on this release. Results land here in under a minute."
            : "No attack has been run for this preset yet. Use “Run the attack again”."}
        </GlassCard>
      ) : (
        <>
          <KpiTile
            key={`a4-${preset}`}
            className="col-span-12 md:col-span-4"
            label="Patients re-identified"
            value={100 * Number(r.release.A4)}
            suffix="%"
            accent={Number(r.release.A4) > 0.2 ? "rose" : "teal"}
            note={
              <>
                down from {pct(Number(r.raw.A4))} on the raw records ({String(r.raw.identified_patients)} of{" "}
                {String(r.raw.patients)} → {String(r.release.identified_patients)})
              </>
            }
          />
          <KpiTile
            key={`res-${preset}`}
            className="col-span-12 md:col-span-4"
            label="Attack resistance"
            value={r.resistance}
            digits={3}
            delay={0.07}
            note="1 − weighted risk over the six attacks, risks as ratios to raw"
          />
          <GlassCard className="col-span-12 flex flex-col gap-3 p-6 md:col-span-4">
            <p className="label">What the attacker got</p>
            <dl className="mt-1 space-y-2.5 text-[14px]">
              {[
                ["Profiles built from the records", String(r.raw.profiles), String(r.release.profiles)],
                [
                  "Global date shift recovered",
                  r.raw.global_shift_recovered ? "yes" : "no",
                  r.release.global_shift_recovered ? "yes" : "no",
                ],
                ["Pseudonyms reversed (A6)", "", r.risks.A6 ? pct(r.risks.A6) : "none"],
                ["Pseudonyms kept under a new secret (A7)", "", r.risks.A7 ? pct(r.risks.A7) : "none"],
              ].map(([k, a, b]) => (
                <div key={k} className="flex items-baseline justify-between gap-3">
                  <dt className="text-text-mid">{k}</dt>
                  <dd className="num shrink-0 text-text-hi">
                    {a && (
                      <>
                        <span className="text-text-lo">{a}</span> <span className="text-text-lo">→</span>{" "}
                      </>
                    )}
                    {b}
                  </dd>
                </div>
              ))}
            </dl>
          </GlassCard>

          <GlassCard className="col-span-12 p-6 xl:col-span-7" aria-label="Attack success, raw against release">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="label">Attack success, raw → Anamika</p>
                <p className="mt-1 text-[13px] text-text-mid">The same attacker, the same voter list, run on both.</p>
              </div>
              <div className="flex items-center gap-4 text-[12px] text-text-mid">
                <span className="flex items-center gap-1.5">
                  <span className="size-2.5 rounded-full" style={{ background: RAW }} />
                  Raw records
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-2.5 rounded-full" style={{ background: REL }} />
                  Anamika release
                </span>
                <button
                  type="button"
                  onClick={() => setTable((t) => !t)}
                  aria-pressed={table}
                  className="flex items-center gap-1.5 rounded-[8px] px-2 py-1 hover:bg-glass-1"
                >
                  <Table2 size={14} strokeWidth={1.5} /> {table ? "Chart" : "Table"}
                </button>
              </div>
            </div>
            {table ? (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="label text-left">
                    <th className="pb-2 font-[600]">Attack</th>
                    <th className="pb-2 text-right font-[600]">Raw</th>
                    <th className="pb-2 text-right font-[600]">Release</th>
                    <th className="pb-2 text-right font-[600]">Risk ratio</th>
                  </tr>
                </thead>
                <tbody>
                  {ATTACKS.map((a) => (
                    <tr key={a.key} className="border-t border-hairline">
                      <td className="py-2 text-text-hi">{a.name}</td>
                      <td className="num py-2 text-right text-text-mid">{pct(Number(r.raw[a.key]))}</td>
                      <td className="num py-2 text-right text-text-hi">{pct(Number(r.release[a.key]))}</td>
                      <td className="num py-2 text-right text-text-mid">{Number(r.risks[a.key]).toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <ul className="space-y-5">
                {ATTACKS.map((a) => {
                  const raw = Number(r.raw[a.key]);
                  const rel = Number(r.release[a.key]);
                  return (
                    <li
                      key={a.key}
                      className="group grid grid-cols-[minmax(0,220px)_1fr_auto] items-center gap-x-5"
                      title={`${a.name}: raw ${pct(raw)}, release ${pct(rel)}`}
                    >
                      <div>
                        <p className="text-[14px] text-text-hi">{a.name}</p>
                        <p className="text-[12px] leading-snug text-text-lo">{a.what}</p>
                      </div>
                      <Dumbbell raw={raw} rel={rel} />
                      <p className="num w-[120px] text-right text-[13px]">
                        <span className="text-text-lo">{pct(raw)}</span> <span className="text-text-lo">→</span>{" "}
                        <span className="text-text-hi">{pct(rel)}</span>
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </GlassCard>

          <GlassCard className="col-span-12 p-6 xl:col-span-5" aria-label="Privacy and utility by preset">
            <p className="label">Privacy ↔ utility, measured</p>
            <p className="mt-1 text-[13px] text-text-mid">
              Each preset, run through the attacker and the clinical probes. Up and right is better.
            </p>
            <div className="mt-4 h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 16, right: 28, bottom: 18, left: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.06)" />
                  <XAxis
                    type="number"
                    dataKey="kept"
                    name="Clinical values kept"
                    unit="%"
                    domain={[96, 100]}
                    ticks={[96, 97, 98, 99, 100]}
                    tick={{ fill: "#8296AC", fontSize: 12 }}
                    stroke="rgba(255,255,255,0.12)"
                    label={{
                      value: "Clinical values kept",
                      position: "insideBottom",
                      offset: -10,
                      fill: "#8296AC",
                      fontSize: 12,
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="resistance"
                    name="Attack resistance"
                    domain={[0.5, 1]}
                    ticks={[0.5, 0.6, 0.7, 0.8, 0.9, 1]}
                    tick={{ fill: "#8296AC", fontSize: 12 }}
                    stroke="rgba(255,255,255,0.12)"
                    width={44}
                  />
                  <ZAxis range={[110, 110]} />
                  <Tooltip
                    cursor={{ stroke: "rgba(255,255,255,0.15)" }}
                    contentStyle={{
                      background: "#102036",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 10,
                      color: "#E8F1F8",
                      fontSize: 12,
                    }}
                    itemStyle={{ color: "#E8F1F8" }}
                  />
                  <Scatter
                    data={points}
                    fill={REL}
                    stroke="#0A1424"
                    strokeWidth={2}
                    shape={(props: { cx?: number; cy?: number; payload?: { key: string; name: string } }) => (
                      <g>
                        <text
                          x={props.cx}
                          y={(props.cy ?? 0) - 16}
                          textAnchor="middle"
                          fill={props.payload?.key === preset ? "#E8F1F8" : "#9FB3C8"}
                          fontSize={12}
                        >
                          {props.payload?.name}
                        </text>
                        <circle
                          cx={props.cx}
                          cy={props.cy}
                          r={props.payload?.key === preset ? 8 : 6}
                          fill={REL}
                          stroke={props.payload?.key === preset ? "#E8F1F8" : "#0A1424"}
                          strokeWidth={2}
                          style={{ cursor: "pointer" }}
                          onClick={() => props.payload && setPreset(props.payload.key)}
                        />
                      </g>
                    )}
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>
        </>
      )}
    </div>
  );
}
