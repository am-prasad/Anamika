#!/usr/bin/env node
/**
 * One-command demo: starts the Anamika FastAPI service (port 8001) and the console
 * (`next start`, port 3000), fully offline. Works on Linux, macOS and Windows.
 *
 *   npm run demo                       # uses ../datasets (or ANAMIKA_DATASETS_DIR)
 *
 * On first run it creates dashboard/.env.local with a random API key and master secret;
 * the key stays server-side (Route Handlers), the browser never sees it.
 */
import { spawn, spawnSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dash = resolve(here, "..");
const repo = resolve(dash, "..");
const backend = join(repo, "backend");
const envFile = join(dash, ".env.local");
const win = process.platform === "win32";

function readEnv(file) {
  if (!existsSync(file)) return {};
  return Object.fromEntries(
    readFileSync(file, "utf8").split(/\r?\n/).filter((l) => l.includes("=") && !l.startsWith("#"))
      .map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1)]),
  );
}

let env = readEnv(envFile);
if (!env.ANAMIKA_API_KEY || !env.ANAMIKA_MASTER_SECRET) {
  env = {
    ANAMIKA_API_URL: "http://127.0.0.1:8001",
    ANAMIKA_API_KEY: `console-${randomBytes(12).toString("hex")}`,
    ANAMIKA_MASTER_SECRET: randomBytes(32).toString("base64url"),
    ...env,
  };
  writeFileSync(envFile, Object.entries(env).map(([k, v]) => `${k}=${v}`).join("\n") + "\n");
  console.log("created dashboard/.env.local (demo key + master secret)");
}

const datasets = process.env.ANAMIKA_DATASETS_DIR ?? env.ANAMIKA_DATASETS_DIR ?? join(repo, "datasets");
if (!existsSync(datasets)) {
  console.error(`No datasets folder at ${datasets}.\nCopy the organiser practice set: datasets/practice/{input,truth,attacker} (see dashboard/README.md).`);
  process.exit(1);
}

const python = env.ANAMIKA_PYTHON ?? join(backend, ".venv", win ? "Scripts\\python.exe" : "bin/python");
const apiEnv = {
  ...process.env,
  ANAMIKA_ENV: "development",
  ANAMIKA_API_KEYS_SHA256: createHash("sha256").update(env.ANAMIKA_API_KEY).digest("hex"),
  ANAMIKA_MASTER_SECRET: env.ANAMIKA_MASTER_SECRET,
  ANAMIKA_DATASETS_DIR: datasets,
  ANAMIKA_DATA_DIR: join(backend, ".data"),
  ANAMIKA_ALLOW_ORIGINALS: "true", // demo only: synthetic datasets, refused in production
  ANAMIKA_MAX_ACTIVE_JOBS_PER_PRINCIPAL: "8",
  ANAMIKA_INLINE_CONCURRENCY: "2",
  ANAMIKA_RATE_DEFAULT: "600/minute",
  ANAMIKA_TRUSTED_HOSTS: "localhost,127.0.0.1",
};

if (!existsSync(join(dash, ".next", "BUILD_ID"))) {
  console.log("building the console (production)…");
  const b = spawnSync(win ? "npm.cmd" : "npm", ["run", "build"], { cwd: dash, stdio: "inherit", env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" } });
  if (b.status !== 0) process.exit(b.status ?? 1);
}

const api = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"], { cwd: backend, env: apiEnv, stdio: "inherit" });
const web = spawn(win ? "npx.cmd" : "npx", ["next", "start", "-p", "3000"], {
  cwd: dash, stdio: "inherit",
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", ANAMIKA_API_URL: env.ANAMIKA_API_URL, ANAMIKA_API_KEY: env.ANAMIKA_API_KEY },
});
console.log("Anamika console → http://localhost:3000  (API on 127.0.0.1:8001)");
const stop = () => { api.kill(); web.kill(); process.exit(0); };
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
api.on("exit", (c) => { console.error(`API exited (${c})`); web.kill(); process.exit(c ?? 1); });
web.on("exit", (c) => { api.kill(); process.exit(c ?? 0); });
