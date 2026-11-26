import { AttackSimulator, type PresetAttack } from "@/components/attack/AttackSimulator";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { attackByPreset, listDatasets, listPresets } from "@/lib/server/anamika";
import type { AttackResult, Job, Preset } from "@/lib/types";

export const metadata = { title: "Attack Simulator" };
export const dynamic = "force-dynamic";

const ORDER = ["strict", "balanced", "research"];

export default async function AttackPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const dataset = typeof sp.dataset === "string" ? sp.dataset : "practice";
  const preset = typeof sp.preset === "string" ? sp.preset : "balanced";

  let jobs: Record<string, Job> = {};
  let presets: Preset[] = [];
  let hasAttacker = true;
  try {
    [jobs, presets] = await Promise.all([attackByPreset(dataset), listPresets()]);
    hasAttacker = (await listDatasets()).find((d) => d.name === dataset)?.has_attacker ?? false;
  } catch {
    return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload." />;
  }
  if (!hasAttacker) {
    return <EmptyState title={`No attacker files for ${dataset}`} body="The attack needs the voter list and the attacker's known facts. The practice dataset ships with them." />;
  }

  const names = [...new Set([...ORDER, ...presets.map((p) => p.name)])].filter((n) => presets.some((p) => p.name === n));
  const attacks: PresetAttack[] = names.map((n) => {
    const a = jobs[n]?.verification?.attack as AttackResult | { available: false } | undefined;
    return { preset: n, status: jobs[n]?.status ?? "none", result: a && "resistance" in a ? a : null };
  });

  return (
    <>
      <PageHeader
        eyebrow="Attack Simulator"
        title="We attacked our own release."
        lede="The published re-identification attacker, run on the raw records and on Anamika's release with the same voter list and the same known facts. Switch the policy to see what each one buys and costs."
        explainTitle="What the attacker knows and does"
        explain={
          <div className="space-y-4">
            <p>
              <span className="text-text-hi">Knowledge.</span> A voter list (name, sex, age, village) and, for some targets, facts a
              neighbour would know: the visit date, the hospital, a rare condition, the length of stay.
            </p>
            <p>
              <span className="text-text-hi">A1 to A5</span> try to put a name back on a record: surviving IDs, registry linkage, pooling
              records into profiles, and a targeted attack that first tries to undo a single global date shift. Anamika shifts each patient
              by their own keyed offset, so there is no single shift to undo.
            </p>
            <p>
              <span className="text-text-hi">A6 and A7</span> attack the pseudonyms: can they be reversed from the originals, and do they
              survive a new secret? HMAC under a run secret answers no to both.
            </p>
            <p className="text-text-lo">
              Risks are ratios to the raw records, as the organisers score them. Resistance is one minus their weighted sum. This is our
              implementation of the published attacks, run locally on synthetic data.
            </p>
          </div>
        }
        aside={<StatusPill kind="info">Synthetic voter list</StatusPill>}
      />
      <AttackSimulator dataset={dataset} initial={names.includes(preset) ? preset : names[0]} attacks={attacks} presets={presets} />
    </>
  );
}
