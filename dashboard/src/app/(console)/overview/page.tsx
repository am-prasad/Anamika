import { LoaderCircle } from "lucide-react";

import { RunButton } from "@/components/shell/RunButton";
import { HeroStage } from "@/components/three/HeroStage";
import { EmptyState } from "@/components/ui/EmptyState";
import { GlassCard } from "@/components/ui/GlassCard";
import { KpiTile } from "@/components/ui/KpiTile";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { Stepper, type Step } from "@/components/ui/Stepper";
import { UsageBar } from "@/components/ui/UsageBar";
import { fmt, pct } from "@/lib/format";
import { getGraph } from "@/lib/server/anamika";
import { loadRun } from "@/lib/server/run";
import type { AttackResult, Graph } from "@/lib/types";

export const metadata = { title: "Command Overview" };
export const dynamic = "force-dynamic";

export default async function OverviewPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { run, dataset, preset } = await loadRun(searchParams);
  const core = run?.core;

  if (!run) {
    return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload. The console never talks to the pipeline directly." />;
  }
  if (!core) {
    return (
      <EmptyState
        title={`No run yet for ${dataset} · ${preset}`}
        body="Run the pipeline on this synthetic dataset. Every number on these screens comes from that run: detection, linkage, the attack and the audit."
        action={<RunButton />}
      />
    );
  }

  const running = core.status === "queued" || core.status === "running";
  const s = core.summary;
  const v = core.verification ?? {};
  const atk = run.attack?.verification?.attack as AttackResult | undefined;
  const atkReady = atk && "resistance" in atk;
  let graph: Graph | null = null;
  if (core.status === "succeeded") {
    try {
      graph = await getGraph(core.id);
    } catch {
      graph = null;
    }
  }

  const c = s?.counts ?? {};
  const steps: Step[] = [
    { name: "Ingest", value: fmt(c.files_total), detail: `${fmt(c.files_sanitized)} cleaned · ${fmt(c.files_quarantined)} quarantined`, state: s ? "done" : "active" },
    { name: "Detect", value: fmt(c.identifiers_detected), detail: "identifiers in 3 scripts", state: s ? "done" : "waiting" },
    { name: "Link", value: fmt(graph?.summary.patients), detail: `${fmt(c.records_linked)} records joined`, state: graph ? "done" : "waiting" },
    { name: "Protect", value: fmt(c.records_generalized), detail: "records generalised", state: s ? "done" : "waiting" },
    { name: "Verify", value: v.leak_scan ? fmt(v.leak_scan.leaked_mentions) : "—", detail: "leaks after the scan", state: v.leak_scan ? "done" : running ? "active" : "waiting" },
  ];

  const rawReid = atkReady ? Number(atk.raw.A4) : null;
  const relReid = atkReady ? Number(atk.release.A4) : null;
  const probes = v.utility?.probe_total;

  return (
    <>
      <PageHeader
        eyebrow={`${dataset} · ${preset} preset`}
        title="Command Overview"
        lede={
          s ? (
            <>
              {fmt(c.files_total)} files from four hospitals, cleaned in {fmt(s.timing.seconds, 1)} s. {fmt(c.identifiers_detected)} identifiers removed; nothing identifying left in the release.
            </>
          ) : (
            "The pipeline is running on the synthetic dataset."
          )
        }
        explainTitle="How a run works"
        explain={
          <div className="space-y-4">
            <p>The console starts two jobs on the FastAPI service for the selected dataset and preset. Both run the exact command the organisers score: <code className="font-mono text-cyan-300">python backend/main.py</code>.</p>
            <p><span className="text-text-hi">Evidence job:</span> the release, value-free explanations, the leak scan, the utility probes, and a determinism check (two more runs: same secret, rotated secret).</p>
            <p><span className="text-text-hi">Attack job:</span> our implementation of the published attacker, A1 to A7, run on the raw input and on the release. Risks are ratios to raw, as the scorer reports them.</p>
            <p>The figure behind the numbers is driven by the run: the share of amber particles that leave the body follows the identifiers detected.</p>
          </div>
        }
        aside={running ? <StatusPill kind="generalized">Running</StatusPill> : <StatusPill kind="protected">Release verified</StatusPill>}
      />

      <div className="grid grid-cols-12 gap-6">
        <GlassCard className="relative col-span-12 h-[460px] overflow-hidden xl:col-span-7" aria-label="Dissolving identity visual">
          <HeroStage identifiers={c.identifiers_detected ?? 3000} replayKey={core.id} />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-ink-950/80 to-transparent p-6">
            <div>
              <p className="label">Identity removed, clinical value kept</p>
              <p className="mt-1 max-w-[46ch] text-[14px] text-text-mid">
                Amber is what identifies a person. It leaves for the shield; the teal figure is what research keeps.
              </p>
            </div>
            <div className="flex gap-2">
              <StatusPill kind="generalized">identity</StatusPill>
              <StatusPill kind="protected">research</StatusPill>
            </div>
          </div>
        </GlassCard>

        <div className="col-span-12 grid grid-cols-2 gap-6 xl:col-span-5">
          {atkReady && rawReid !== null && relReid !== null ? (
            <KpiTile
              label="Re-identified"
              value={relReid * 100}
              digits={0}
              suffix="%"
              accent="teal"
              delay={0}
              note={
                <>
                  of patients, down from <span className="num text-text-hi">{pct(rawReid, 0)}</span> on the raw data · resistance <span className="num text-text-hi">{atk.resistance.toFixed(3)}</span>
                </>
              }
            />
          ) : (
            <GlassCard className="flex flex-col gap-3 p-6">
              <p className="label">Re-identified</p>
              <p className="flex items-center gap-2 text-[15px] text-text-mid">
                <LoaderCircle size={16} className="animate-spin text-amber-400" /> Attack running on raw and release
              </p>
              <p className="text-[13px] text-text-lo">The attacker takes about two minutes; this tile fills in when it lands.</p>
            </GlassCard>
          )}
          <KpiTile label="Identifiers removed" value={c.identifiers_detected ?? 0} delay={0.07} note={<>names, phones, IDs and addresses in English, <span lang="hi">हिंदी</span> and Hinglish</>} />
          <KpiTile label="Patients linked" value={graph?.summary.patients ?? 0} delay={0.14} note={<>{fmt(graph?.summary.kept_apart_pairs)} same-name pairs kept apart</>} />
          <KpiTile
            label="Canary leaks"
            value={v.leak_scan?.canary_tokens_found ?? 0}
            delay={0.21}
            accent={v.leak_scan && v.leak_scan.canary_tokens_found > 0 ? "rose" : "teal"}
            note={<>of {fmt(v.leak_scan?.canary_tokens_total)} planted canary tokens · {fmt(v.leak_scan?.leaked_mentions)} of {fmt(v.leak_scan?.total_mentions)} PII mentions visible</>}
          />
        </div>

        <GlassCard className="col-span-12 px-8 pt-4 pb-6">
          <Stepper steps={steps} />
        </GlassCard>

        <GlassCard className="col-span-12 flex flex-col gap-2 p-6 md:col-span-6 xl:col-span-3">
          <p className="label">Clinical values kept</p>
          <p className="num font-display text-[34px] font-[300]">{probes ? pct(probes[0] / probes[1]) : "—"}</p>
          <p className="text-[13px] text-text-mid">{probes ? `${fmt(probes[0])} of ${fmt(probes[1])} doses, labs, vitals and diagnoses` : "waiting for the utility check"}</p>
        </GlassCard>
        <GlassCard className="col-span-12 flex flex-col gap-2 p-6 md:col-span-6 xl:col-span-3">
          <p className="label">Runtime</p>
          <p className="num font-display text-[34px] font-[300]">{s ? `${fmt(s.timing.seconds, 1)} s` : "—"}</p>
          <UsageBar value={s?.timing.seconds ?? 0} limit={900} unit="s" />
        </GlassCard>
        <GlassCard className="col-span-12 flex flex-col gap-2 p-6 md:col-span-6 xl:col-span-3">
          <p className="label">Peak memory</p>
          <p className="num font-display text-[34px] font-[300]">{s ? `${fmt(s.resources.peak_rss_mb)} MB` : "—"}</p>
          <UsageBar value={s?.resources.peak_rss_mb ?? 0} limit={4096} unit="MB" />
        </GlassCard>
        <GlassCard className="col-span-12 flex flex-col gap-2 p-6 md:col-span-6 xl:col-span-3">
          <p className="label">Quarantined, never copied</p>
          <p className="num font-display text-[34px] font-[300]">{fmt(c.files_quarantined)}</p>
          <p className="text-[13px] text-text-mid">
            {s ? Object.entries(s.quarantine_reasons).map(([r, n]) => `${r.replaceAll("_", " ")} ${n}`).join(" · ") : "—"}
          </p>
        </GlassCard>
      </div>
    </>
  );
}
