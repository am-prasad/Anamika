import "server-only";

import { NextResponse } from "next/server";

import { ApiError } from "./anamika";

const SAFE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;
const JOB = /^[0-9a-f]{32}$/;

/** Validate a dataset / preset name before it is forwarded. */
export const safeName = (v: string | null, fallback: string) => (v && SAFE.test(v) ? v : fallback);
export const safeJob = (v: string | null) => (v && JOB.test(v) ? v : null);

/** Run a handler and map backend errors to small JSON codes (never stack traces). */
export async function handle<T>(fn: () => Promise<T>): Promise<NextResponse> {
  try {
    return NextResponse.json(await fn(), { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 500;
    const code = e instanceof ApiError ? e.code : "console_error";
    return NextResponse.json({ error: code }, { status });
  }
}
