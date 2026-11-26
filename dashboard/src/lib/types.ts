/** Shapes returned by the Anamika FastAPI service (backend/app). Values are never PII. */

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface AttackResult {
  risk: number;
  resistance: number;
  risks: Record<string, number>;
  raw: Record<string, number | boolean>;
  release: Record<string, number | boolean>;
}

export interface UtilityResult {
  probes: Record<string, [number, number]>;
  probe_total: [number, number];
  token_retention: number;
  clean_token_retention: number;
  los?: { before: number; after: number }[];
  age_truth?: [number, number];
}

export interface Verification {
  determinism?: { files_total: number; files_identical: number; exit_code: number };
  rotation?: { files_changed: number; pseudonyms_total: number; pseudonyms_reused: number };
  leak_scan?: {
    leaked_mentions: number;
    total_mentions: number;
    canary_tokens_found: number;
    canary_tokens_total: number;
    side_channel_hits: Record<string, number>;
    by_script?: Record<string, [number, number]>;
    by_type?: Record<string, [number, number]>;
  };
  utility?: UtilityResult;
  attack?: AttackResult | { available: false };
}

export interface JobSummary {
  counts: Record<string, number>;
  entities: Record<string, number>;
  timing: { seconds: number };
  resources: { peak_rss_mb: number };
  quarantine_reasons: Record<string, number>;
  wall_seconds: number;
  policy: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  source: string;
  release: string;
  options: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  input_files: number;
  error: string | null;
  summary: JobSummary | null;
  verification: Verification | null;
}

export interface Preset {
  name: string;
  description: string;
  location_level: string;
  age_band_years: number;
  pin_digits: number;
  rare_k: number;
  measured: Record<string, number>;
}

export interface Dataset {
  name: string;
  files: number;
  has_answer_key: boolean;
  has_attacker: boolean;
}

export interface Span {
  start: number;
  end: number;
  type: string;
  rule?: string;
}

export interface Explain {
  input_sha256: string;
  output: string;
  format: string;
  records: number;
  spans?: Span[];
  kept?: Span[];
  dates?: { start: number; end: number }[];
  columns?: { index: number; role: string }[];
  fields?: { path: string; role: string; count: number }[];
}

export interface CompareDoc {
  path: string;
  original: string;
  sanitized: string;
  explain: Explain | null;
}

export interface GraphNode {
  id: number;
  file: string;
  loc: string;
  patient: string | null;
  evidence: string[];
}

export interface Graph {
  nodes: GraphNode[];
  edges: { source: number; target: number; type: string }[];
  kept_apart: { a: number; b: number; patient_a: string | null; patient_b: string | null; shared: string; conflict: string[] }[];
  summary: { records: number; linked: number; patients: number; largest_cluster: number; kept_apart_pairs: number };
}

export interface ReleaseFile {
  path: string;
  bytes: number;
  sha256: string;
}

export interface Report {
  files: { input_sha256: string; output: string | null; status: string; reason?: string }[];
  counts: Record<string, number>;
  entities: Record<string, number>;
  timing: { seconds: number };
  resources: { peak_rss_mb: number };
}

/** The two jobs behind one console "run": fast evidence job + slower attack job. */
export interface Run {
  dataset: string;
  preset: string;
  core: Job | null;
  attack: Job | null;
}
