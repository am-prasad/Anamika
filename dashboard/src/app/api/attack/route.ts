import { attackByPreset, startAttack } from "@/lib/server/anamika";
import { handle, safeName } from "@/lib/server/route";

export const dynamic = "force-dynamic";

/** GET: latest attack job per preset for ?dataset. POST: start an attack run for a preset. */
export async function GET(req: Request) {
  return handle(() => attackByPreset(safeName(new URL(req.url).searchParams.get("dataset"), "practice")));
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { dataset?: string; preset?: string };
  return handle(() => startAttack(safeName(body.dataset ?? null, "practice"), safeName(body.preset ?? null, "balanced")));
}
