import "server-only";

import type { CompareDoc, Dataset, Graph, Job, Preset, ReleaseFile, Report, Run } from "@/lib/types";

/**
 * Server-only client for the Anamika FastAPI service. The URL and API key live in server
 * environment variables and never reach the browser: client components talk to the
 * Next.js Route Handlers in `app/api/*`, which call these functions.
 */
const BASE = process.env.ANAMIKA_API_URL ?? "http://127.0.0.1:8001";
const KEY = process.env.ANAMIKA_API_KEY ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "X-API-Key": KEY, "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(503, "backend_unreachable");
  }
  if (!res.ok) {
    let code = `http_${res.status}`;
    try {
      code = ((await res.json()) as { error?: string }).error ?? code;
    } catch {
      /* keep status code */
    }
    throw new ApiError(res.status, code);
  }
  return (await res.json()) as T;
}

export const listDatasets = () => call<{ items: Dataset[] }>("/api/v1/datasets").then((r) => r.items);
export const listPresets = () => call<{ items: Preset[] }>("/api/v1/policy/presets").then((r) => r.items);
export const listJobs = () => call<{ items: Job[] }>("/api/v1/jobs").then((r) => r.items);
export const getJob = (id: string) => call<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`);
export const getReport = (id: string) => call<Report>(`/api/v1/jobs/${encodeURIComponent(id)}/report`);
export const getGraph = (id: string) => call<Graph>(`/api/v1/jobs/${encodeURIComponent(id)}/graph`).then(keptApartPeople);

/**
 * A refused weak link between records that stronger evidence later joined is not a refused
 * merge. Keep only pairs that ended as two different patients, counted once per patient pair.
 */
function keptApartPeople(g: Graph): Graph {
  const apart = g.kept_apart.filter((k) => !(k.patient_a && k.patient_a === k.patient_b));
  const people = new Set(apart.map((k) => [k.patient_a ?? `r${k.a}`, k.patient_b ?? `r${k.b}`].sort().join("|")));
  return { ...g, kept_apart: apart, summary: { ...g.summary, kept_apart_pairs: people.size } };
}
export const listFiles = (id: string) =>
  call<{ items: ReleaseFile[] }>(`/api/v1/jobs/${encodeURIComponent(id)}/files`).then((r) => r.items);
export const compareDoc = (id: string, path: string) =>
  call<CompareDoc>(
    `/api/v1/jobs/${encodeURIComponent(id)}/compare/${path.split("/").map(encodeURIComponent).join("/")}`,
  );

/** Start one console run: a fast evidence job and an attack job for the same dataset + preset. */
export async function startRun(dataset: string, preset: string): Promise<{ core: Job; attack: Job | null }> {
  const core = await call<Job>("/api/v1/jobs/from-dataset", {
    method: "POST",
    body: JSON.stringify({
      dataset,
      policy: preset,
      explain: true,
      utility: true,
      leak_scan: true,
      verify_determinism: true,
    }),
  });
  let attack: Job | null = null;
  try {
    attack = await call<Job>("/api/v1/jobs/from-dataset", {
      method: "POST",
      body: JSON.stringify({ dataset, policy: preset, attack: true, verify_determinism: true }),
    });
  } catch {
    attack = null; // capacity or no attacker files: the core run still stands
  }
  return { core, attack };
}

function matches(j: Job, dataset: string, preset: string): boolean {
  return j.source === `dataset:${dataset}` && (j.options.policy ?? "balanced") === preset;
}

/** The latest run for a dataset + preset (jobs are listed newest first). */
export async function currentRun(dataset: string, preset: string): Promise<Run> {
  const jobs = await listJobs();
  const core = jobs.find((j) => matches(j, dataset, preset) && j.options.explain === true) ?? null;
  const attack = jobs.find((j) => matches(j, dataset, preset) && j.options.attack === true) ?? null;
  return { dataset, preset, core, attack };
}

/** Latest finished attack result per preset (Attack Simulator switches between them). */
export async function attackByPreset(dataset: string): Promise<Record<string, Job>> {
  const jobs = await listJobs();
  const out: Record<string, Job> = {};
  for (const j of jobs) {
    if (j.source !== `dataset:${dataset}` || j.options.attack !== true) continue;
    const p = String(j.options.policy ?? "balanced");
    if (!out[p] || (out[p].status !== "succeeded" && j.status === "succeeded")) out[p] = j;
  }
  return out;
}

export async function startAttack(dataset: string, preset: string): Promise<Job> {
  return call<Job>("/api/v1/jobs/from-dataset", {
    method: "POST",
    body: JSON.stringify({ dataset, policy: preset, attack: true, verify_determinism: true }),
  });
}
