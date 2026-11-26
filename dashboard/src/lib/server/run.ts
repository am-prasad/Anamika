import "server-only";

import type { Run } from "@/lib/types";

import { currentRun } from "./anamika";

type SP = Promise<Record<string, string | string[] | undefined>>;

const one = (v: string | string[] | undefined, d: string) => (typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(v) ? v : d);

/** Resolve dataset / preset from the URL and load the matching run (null when offline). */
export async function loadRun(searchParams: SP): Promise<{ run: Run | null; dataset: string; preset: string }> {
  const sp = await searchParams;
  const dataset = one(sp.dataset, "practice");
  const preset = one(sp.preset, "balanced");
  try {
    return { run: await currentRun(dataset, preset), dataset, preset };
  } catch {
    return { run: null, dataset, preset };
  }
}
