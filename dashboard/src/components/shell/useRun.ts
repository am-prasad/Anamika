"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import type { Run } from "@/lib/types";

const fetcher = async (url: string) => {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { error?: string }).error ?? "error");
  return r.json();
};

const ACTIVE = new Set(["queued", "running"]);

/** Dataset + preset from the URL (shareable demo state), with defaults. */
export function useSelection() {
  const p = useSearchParams();
  return { dataset: p.get("dataset") ?? "practice", preset: p.get("preset") ?? "balanced" };
}

/** Polls the current run while it is active and refreshes server components when it lands. */
export function useRun() {
  const { dataset, preset } = useSelection();
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const key = `/api/run?dataset=${encodeURIComponent(dataset)}&preset=${encodeURIComponent(preset)}`;
  const { data, error, mutate } = useSWR<Run>(key, fetcher, {
    refreshInterval: (d) => (d && (ACTIVE.has(d.core?.status ?? "") || ACTIVE.has(d.attack?.status ?? "")) ? 1500 : 0),
    revalidateOnFocus: false,
  });

  const prev = useRef<string>("");
  useEffect(() => {
    const sig = `${data?.core?.id}:${data?.core?.status}:${data?.attack?.status}`;
    if (prev.current && prev.current !== sig) router.refresh();
    prev.current = sig;
  }, [data, router]);

  const start = useCallback(async () => {
    setStarting(true);
    try {
      await fetch("/api/run", { method: "POST", body: JSON.stringify({ dataset, preset }) });
      await mutate();
    } finally {
      setStarting(false);
    }
  }, [dataset, preset, mutate]);

  const running = starting || ACTIVE.has(data?.core?.status ?? "") || ACTIVE.has(data?.attack?.status ?? "");
  return { run: data, error: error as Error | undefined, start, running, starting };
}
