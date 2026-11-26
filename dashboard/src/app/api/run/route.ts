import { currentRun, startRun } from "@/lib/server/anamika";
import { handle, safeName } from "@/lib/server/route";

export const dynamic = "force-dynamic";

/** GET: the latest run for ?dataset&preset. POST: start a new run (evidence + attack jobs). */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  return handle(() => currentRun(safeName(q.get("dataset"), "practice"), safeName(q.get("preset"), "balanced")));
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { dataset?: string; preset?: string };
  return handle(() => startRun(safeName(body.dataset ?? null, "practice"), safeName(body.preset ?? null, "balanced")));
}
