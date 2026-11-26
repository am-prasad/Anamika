import { RunButton } from "@/components/shell/RunButton";
import { RedactionStudio } from "@/components/redaction/RedactionStudio";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill } from "@/components/ui/StatusPill";
import { compareDoc, listFiles } from "@/lib/server/anamika";
import { loadRun } from "@/lib/server/run";
import type { CompareDoc, ReleaseFile } from "@/lib/types";

export const metadata = { title: "Redaction Studio" };
export const dynamic = "force-dynamic";

type SP = Promise<Record<string, string | string[] | undefined>>;

/** A free-text note is the best first impression: names, relatives, Hinglish, doses. */
function defaultDoc(files: ReleaseFile[]): string {
  return (files.find((f) => f.path.startsWith("notes/")) ?? files.find((f) => f.path.endsWith(".txt")) ?? files[0])?.path ?? "";
}

export default async function RedactionPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const { run, dataset, preset } = await loadRun(searchParams);
  const core = run?.core;
  if (!run) return <EmptyState title="The Anamika service is not reachable" body="Start the backend (npm run demo starts both) and reload." />;
  if (!core || core.status !== "succeeded") {
    return (
      <EmptyState
        title={core ? "The run is still in progress" : `No run yet for ${dataset} · ${preset}`}
        body="The studio compares each original file with its release once the evidence job finishes."
        action={core ? undefined : <RunButton />}
      />
    );
  }

  let files: ReleaseFile[] = [];
  try {
    files = await listFiles(core.id);
  } catch {
    files = [];
  }
  const requested = typeof sp.doc === "string" ? sp.doc : "";
  const selected = files.some((f) => f.path === requested) ? requested : defaultDoc(files);
  let doc: CompareDoc | null = null;
  let docError = false;
  if (selected) {
    try {
      doc = await compareDoc(core.id, selected);
    } catch {
      docError = true;
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Redaction Studio"
        title="Every identifier out, every clinical value in."
        lede={
          <>
            Original on the left, the release on the right. Teal was removed, amber was generalised, the green outline is what we
            deliberately kept: doses, vitals, doctors, diseases.
          </>
        }
        explainTitle="How a span is decided"
        explain={
          <div className="space-y-4">
            <p>
              <span className="text-text-hi">Pass A learns.</span> Structured fields are classified by their header and by profiling their values,
              so unseen labels still work. Names found in fields feed a run-time lexicon; that lexicon then finds the same people in free text,
              including <span lang="hi">देवनागरी</span> spellings and Hinglish forms such as &ldquo;sahab&rdquo; and &ldquo;ji&rdquo;.
            </p>
            <p>
              <span className="text-text-hi">Meaning traps.</span> &ldquo;C/O fever&rdquo; is a complaint, &ldquo;C/O Ramesh&rdquo; is a relative.
              &ldquo;Dr.&rdquo; keeps a name, &ldquo;S/o&rdquo; removes it. A number next to mg, BD or BP is a dose or a vital, never a phone.
            </p>
            <p>
              <span className="text-text-hi">Pass B rewrites.</span> Patients become their keyed pseudonym <code className="font-mono text-cyan-300">PSN-XXXXXX</code>,
              dates move by that patient&rsquo;s own offset, ages become bands, places rise to the policy level.
            </p>
            <p className="text-text-lo">
              Hover any highlight to see the entity type and the rule that fired. The explanations hold offsets and rule ids only, never values.
              Originals are served only in this local demo mode and never in production.
            </p>
          </div>
        }
        aside={<StatusPill kind="info">{files.length} files in the release</StatusPill>}
      />
      {docError ? (
        <EmptyState title="This file cannot be compared" body="Originals are only served in local demo mode. Start the backend with npm run demo." />
      ) : (
        <RedactionStudio files={files} doc={doc} selected={selected} jobId={core.id} />
      )}
    </>
  );
}
