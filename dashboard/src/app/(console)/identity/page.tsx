import { IdentityExplorer } from "@/components/identity/IdentityExplorer";
import { RunButton } from "@/components/shell/RunButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { fmt } from "@/lib/format";
import { getGraph } from "@/lib/server/anamika";
import { loadRun } from "@/lib/server/run";
import type { Graph } from "@/lib/types";

export const metadata = { title: "Identity Graph" };
export const dynamic = "force-dynamic";

export default async function IdentityPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { run, dataset, preset } = await loadRun(searchParams);
  const core = run?.core;
  if (!run) return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload." />;
  if (!core || core.status !== "succeeded") {
    return (
      <EmptyState
        title={core ? "The run is still in progress" : `No run yet for ${dataset} · ${preset}`}
        body="The graph appears once the evidence job has linked every record."
        action={core ? undefined : <RunButton />}
      />
    );
  }
  let graph: Graph | null = null;
  try {
    graph = await getGraph(core.id);
  } catch {
    graph = null;
  }
  if (!graph) return <EmptyState title="No linkage graph for this run" body="Start a new run from the top bar; the evidence job writes the graph." action={<RunButton />} />;

  return (
    <>
      <PageHeader
        eyebrow="Identity Graph"
        title="One patient, every hospital, one pseudonym."
        lede={
          <>
            {fmt(graph.summary.records)} records from four hospitals in English and <span lang="hi">हिंदी</span> resolve to{" "}
            {fmt(graph.summary.patients)} patients. When the evidence is weak the record stays unlinked; when it conflicts, two people stay two people.
          </>
        }
        explainTitle="How records are linked"
        explain={
          <div className="space-y-4">
            <p>
              <span className="text-text-hi">Strong IDs first.</span> Records that share an Aadhaar, ABHA or a hospital&rsquo;s own patient ID
              are joined with union-find. Two different IDs of the same kind are a cannot-link constraint for the whole cluster.
            </p>
            <p>
              <span className="text-text-hi">Names across scripts.</span> <span lang="hi">मोहम्मद आरिफ</span>, &ldquo;Md. Arif&rdquo; and
              &ldquo;Mohammad Arif&rdquo; share one key: transliterated to Latin, honorifics stripped, spelling variants folded, reduced to a
              consonant skeleton. A name alone never links; it needs a date of birth, a village with a compatible age, or a relative.
            </p>
            <p>
              <span className="text-text-hi">Precision first.</span> Weak keys pass a Fellegi&ndash;Sunter score and every merge is checked against
              the whole cluster, so links never chain into a wrong merge. On the practice answer key: 0 false merges.
            </p>
            <p>
              <span className="text-text-hi">Pseudonyms</span> are HMAC-SHA256 of the cluster under a key derived from the run secret. A new secret
              changes every pseudonym; the same secret reproduces them byte for byte.
            </p>
          </div>
        }
        aside={<StatusPill kind="protected">{fmt(graph.summary.kept_apart_pairs)} wrong merges refused</StatusPill>}
      />
      <IdentityExplorer graph={graph} />
    </>
  );
}
