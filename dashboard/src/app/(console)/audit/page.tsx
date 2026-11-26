import { ArrowRight, FileWarning, KeyRound } from "lucide-react";

import { RunButton } from "@/components/shell/RunButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { GlassCard } from "@/components/ui/GlassCard";
import { KpiTile } from "@/components/ui/KpiTile";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { fmt } from "@/lib/format";
import { getReport } from "@/lib/server/anamika";
import { loadRun } from "@/lib/server/run";
import type { Report } from "@/lib/types";

export const metadata = { title: "Security & Audit" };
export const dynamic = "force-dynamic";

const CHANNEL: Record<string, string> = {
  content: "Document text and fields",
  filename: "File names",
  header: "CSV headers",
  key: "JSON keys",
  metadata: "Metadata",
  base64: "Base64 attachments",
};

const REASON: Record<string, string> = {
  unsupported_format: "Format we do not parse (binary, archive, spreadsheet)",
  malformed_json: "JSON that cannot be parsed safely",
  json_too_deep: "JSON nested beyond the safe depth",
  undecodable_text: "Text in no recognisable encoding",
  empty_file: "Empty file",
};

const KEYS: { name: string; use: string }[] = [
  { name: "k_pseudo", use: "HMAC pseudonyms PSN-XXXXXX" },
  { name: "k_shift", use: "per-patient date offsets" },
  { name: "k_file", use: "safe names for files with PII in the name" },
  { name: "k_enc", use: "AES-GCM for anything spilled to temp" },
];

export default async function AuditPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { run, dataset, preset } = await loadRun(searchParams);
  const core = run?.core;
  if (!run) return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload." />;
  if (!core || core.status !== "succeeded") {
    return (
      <EmptyState
        title={core ? "The run is still in progress" : `No run yet for ${dataset} · ${preset}`}
        body="The audit appears once the release, the reruns and the leak scan are done."
        action={core ? undefined : <RunButton />}
      />
    );
  }
  const v = core.verification ?? {};
  const leak = v.leak_scan;
  const det = v.determinism;
  const rot = v.rotation;
  let report: Report | null = null;
  try {
    report = await getReport(core.id);
  } catch {
    report = null;
  }
  const quarantined = (report?.files ?? []).filter((f) => f.status === "quarantined");

  const channels = new Map<string, [number, number]>();
  for (const [k, [l, n]] of Object.entries(leak?.by_type ?? {})) {
    const ch = k.split("/")[1] ?? "content";
    const cur = channels.get(ch) ?? [0, 0];
    channels.set(ch, [cur[0] + l, cur[1] + n]);
  }
  const scripts = Object.entries(leak?.by_script ?? {});
  const side = Object.values(leak?.side_channel_hits ?? {}).reduce((a, b) => a + b, 0);
  const clean = leak && leak.leaked_mentions === 0 && leak.canary_tokens_found === 0 && side === 0;

  return (
    <>
      <PageHeader
        eyebrow="Security & Audit"
        title="Nothing leaks, and you can check it."
        lede="The release is scanned against every identifier in the answer key, in every place one can hide. Two more runs prove it is reproducible and that a new secret changes every pseudonym."
        explainTitle="The security design"
        explain={
          <div className="space-y-4">
            <p>
              <span className="text-text-hi">One secret, read once.</span> <code className="font-mono text-cyan-300">RAKSHA_SECRET</code> comes from the
              environment, never from a file, and is never printed, logged or stored. Four keys are derived from it with HKDF-SHA256, one per job.
            </p>
            <p>
              <span className="text-text-hi">Logs that cannot carry data.</span> The logger only accepts whitelisted templates with counts, stage
              names and hash prefixes. Uncaught errors print the exception type and stage, never a value or a traceback.
            </p>
            <p>
              <span className="text-text-hi">Fail closed.</span> A file we cannot parse safely is quarantined with a reason, never copied. Every
              input file is accounted for in report.json by its SHA-256, never by its name.
            </p>
            <p>
              <span className="text-text-hi">Offline.</span> No network at run time, no language model, input opened read-only.
            </p>
          </div>
        }
        aside={clean ? <StatusPill kind="protected">Release verified</StatusPill> : <StatusPill kind="leak">Check the scan</StatusPill>}
      />

      <div className="grid grid-cols-12 gap-6">
        <KpiTile
          className="col-span-12 sm:col-span-6 xl:col-span-3"
          label="Identifiers leaked"
          value={leak?.leaked_mentions ?? 0}
          accent={leak && leak.leaked_mentions > 0 ? "rose" : "teal"}
          note={leak ? <>of {fmt(leak.total_mentions)} mentions in the answer key</> : "No answer key for this dataset"}
        />
        <KpiTile
          className="col-span-12 sm:col-span-6 xl:col-span-3"
          label="Canaries found"
          value={leak?.canary_tokens_found ?? 0}
          delay={0.07}
          accent={leak && leak.canary_tokens_found > 0 ? "rose" : "teal"}
          note={leak ? <>of {fmt(leak.canary_tokens_total)} planted tokens, searched in outputs and logs</> : "—"}
        />
        <KpiTile
          className="col-span-12 sm:col-span-6 xl:col-span-3"
          label="Byte-identical rerun"
          value={det?.files_identical ?? 0}
          delay={0.14}
          note={det ? <>of {fmt(det.files_total)} files, same input and same secret</> : "Not verified for this run"}
        />
        <KpiTile
          className="col-span-12 sm:col-span-6 xl:col-span-3"
          label="Pseudonyms reused"
          value={rot?.pseudonyms_reused ?? 0}
          delay={0.21}
          accent="teal"
          note={rot ? <>of {fmt(rot.pseudonyms_total)} under a new secret; {fmt(rot.files_changed)} files changed</> : "Not verified for this run"}
        />

        <GlassCard className="col-span-12 p-6 lg:col-span-7" aria-label="Leak scan by channel">
          <p className="label">Where we looked</p>
          <p className="mt-1 text-[13px] text-text-mid">Every channel the organisers name, plus logs, temp files and the report itself.</p>
          <ul className="mt-5 divide-y divide-hairline">
            {[...channels.entries()].map(([ch, [l, n]]) => (
              <li key={ch} className="flex items-center justify-between gap-3 py-2.5 text-[14px]">
                <span className="text-text-hi">{CHANNEL[ch] ?? ch}</span>
                <span className="flex items-center gap-3">
                  <span className="num text-text-mid">
                    {fmt(l)} of {fmt(n)}
                  </span>
                  {l === 0 ? <StatusPill kind="protected">clean</StatusPill> : <StatusPill kind="leak">leak</StatusPill>}
                </span>
              </li>
            ))}
            <li className="flex items-center justify-between gap-3 py-2.5 text-[14px]">
              <span className="text-text-hi">Logs, temp files, report.json, records.jsonl</span>
              <span className="flex items-center gap-3">
                <span className="num text-text-mid">{fmt(side)} hits</span>
                {side === 0 ? <StatusPill kind="protected">clean</StatusPill> : <StatusPill kind="leak">leak</StatusPill>}
              </span>
            </li>
          </ul>
          {scripts.length > 0 && (
            <div className="mt-5 flex flex-wrap gap-2">
              {scripts.map(([s, [l, n]]) => (
                <span key={s} className="glass-1 rounded-full px-3 py-1 text-[12.5px] text-text-mid">
                  <span lang={s === "deva" ? "hi" : undefined} className="text-text-hi">
                    {s === "deva" ? "देवनागरी" : s === "latin" ? "English" : "Hinglish"}
                  </span>{" "}
                  <span className="num">
                    {fmt(l)} of {fmt(n)} leaked
                  </span>
                </span>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard className="col-span-12 p-6 lg:col-span-5" aria-label="Quarantined files">
          <p className="label flex items-center gap-2">
            <FileWarning size={14} strokeWidth={1.5} /> Quarantined, never copied
          </p>
          <p className="mt-1 text-[13px] text-text-mid">
            {fmt(quarantined.length)} of {fmt(report?.files.length ?? core.input_files)} files. Identified by SHA-256 only; no name ever reaches a report.
          </p>
          <ul className="mt-4 space-y-2">
            {quarantined.map((f) => (
              <li key={f.input_sha256} className="glass-1 flex items-center justify-between gap-3 rounded-[12px] px-3 py-2">
                <span className="font-mono text-[12.5px] text-text-mid">{f.input_sha256.slice(0, 12)}…</span>
                <span className="text-right text-[12.5px] text-text-hi">{REASON[f.reason ?? ""] ?? (f.reason ?? "").replaceAll("_", " ")}</span>
              </li>
            ))}
            {quarantined.length === 0 && <li className="text-[13px] text-text-lo">Every file was parsed and sanitised.</li>}
          </ul>
        </GlassCard>

        <GlassCard className="col-span-12 p-6" aria-label="Key design">
          <p className="label flex items-center gap-2">
            <KeyRound size={14} strokeWidth={1.5} /> One secret, four keys, nothing stored
          </p>
          <div className="mt-6 flex flex-col items-stretch gap-4 lg:flex-row lg:items-center">
            <div className="glass-1 rounded-[14px] px-4 py-3 lg:w-[220px]">
              <p className="font-mono text-[13px] text-cyan-300">RAKSHA_SECRET</p>
              <p className="mt-1 text-[12px] text-text-lo">environment only, held in memory</p>
            </div>
            <ArrowRight className="hidden shrink-0 text-text-lo lg:block" size={18} aria-hidden />
            <div className="glass-1 rounded-[14px] px-4 py-3 lg:w-[180px]">
              <p className="font-mono text-[13px] text-text-hi">HKDF-SHA256</p>
              <p className="mt-1 text-[12px] text-text-lo">one label per purpose</p>
            </div>
            <ArrowRight className="hidden shrink-0 text-text-lo lg:block" size={18} aria-hidden />
            <ul className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
              {KEYS.map((k) => (
                <li key={k.name} className="glass-1 rounded-[14px] px-4 py-3">
                  <p className="font-mono text-[13px] text-teal-400">{k.name}</p>
                  <p className="mt-1 text-[12px] text-text-mid">{k.use}</p>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-5 text-[13px] text-text-mid">
            A breach of the release reveals no key: pseudonyms are HMACs, offsets are keyed, and the secret is never written. Rotate the secret and
            every pseudonym and every date offset changes.
          </p>
        </GlassCard>
      </div>
    </>
  );
}
