import { ClinicalIntegrity } from "@/components/clinical/ClinicalIntegrity";
import { RunButton } from "@/components/shell/RunButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { KpiTile } from "@/components/ui/KpiTile";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { fmt, pct } from "@/lib/format";
import { loadRun } from "@/lib/server/run";

export const metadata = { title: "Clinical Integrity" };
export const dynamic = "force-dynamic";

export default async function IntegrityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { run, dataset, preset } = await loadRun(searchParams);
  const core = run?.core;
  if (!run) return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload." />;
  if (!core || core.status !== "succeeded") {
    return (
      <EmptyState
        title={core ? "The run is still in progress" : `No run yet for ${dataset} · ${preset}`}
        body="The clinical probes run once the release is written."
        action={core ? undefined : <RunButton />}
      />
    );
  }
  const u = core.verification?.utility;
  if (!u) {
    return <EmptyState title="No clinical probes for this dataset" body="The probes need an answer key. The practice dataset ships with one." />;
  }
  const [kept, total] = u.probe_total;
  const los = u.los ?? [];
  const losExact = los.filter((p) => p.before === p.after).length;
  const [ageOk, ageN] = u.age_truth ?? [0, 0];

  return (
    <>
      <PageHeader
        eyebrow="Clinical Integrity"
        title="Private enough to share, exact enough to study."
        lede="Doses, vitals, lab values, diagnoses and doctors survive untouched. Dates move, intervals don't. Ages become bands that still contain the true age."
        explainTitle="How utility is measured"
        explain={
          <div className="space-y-4">
            <p>
              <span className="text-text-hi">Probes.</span> The answer key lists every clinically useful value in the input: each dose,
              frequency, vital, lab result, diagnosis, ICD code and treating doctor. A probe passes only if that exact value is still in the
              same record of the release.
            </p>
            <p>
              <span className="text-text-hi">Length of stay.</span> Each patient gets one keyed date offset, applied to every date they have,
              so admission to discharge stays exact to the day.
            </p>
            <p>
              <span className="text-text-hi">Age bands.</span> Every band written into the release is checked against the true age on the
              record&rsquo;s date: it must contain it.
            </p>
            <p className="text-text-lo">
              Losses you see are deliberate policy, labelled where they occur: locations above the policy level are raised, not deleted.
            </p>
          </div>
        }
        aside={<StatusPill kind="kept">{pct(kept / Math.max(1, total))} of clinical values kept</StatusPill>}
      />
      <div className="mb-6 grid grid-cols-12 gap-6">
        <KpiTile className="col-span-12 sm:col-span-6 xl:col-span-3" label="Clinical values kept" value={(100 * kept) / Math.max(1, total)} digits={1} suffix="%" accent="teal" note={<>{fmt(kept)} of {fmt(total)} probes</>} />
        <KpiTile className="col-span-12 sm:col-span-6 xl:col-span-3" label="Length of stay exact" value={losExact} delay={0.07} note={<>of {fmt(los.length)} admissions, to the day</>} />
        <KpiTile className="col-span-12 sm:col-span-6 xl:col-span-3" label="Age bands truthful" value={ageOk} delay={0.14} note={<>of {fmt(ageN)} bands contain the true age</>} />
        <KpiTile className="col-span-12 sm:col-span-6 xl:col-span-3" label="Text retained" value={100 * u.token_retention} digits={1} suffix="%" delay={0.21} note={<>{pct(u.clean_token_retention)} on documents with no personal data</>} />
      </div>
      <ClinicalIntegrity u={u} />
    </>
  );
}
