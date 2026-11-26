"use client";

import { EmptyState } from "@/components/ui/EmptyState";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <EmptyState
      title="This screen could not load"
      body="The console could not reach the Anamika service or the run data was incomplete. Start the backend and try again."
      action={
        <button type="button" onClick={reset} className="glass-1 mt-2 h-10 rounded-[12px] px-4 text-[14px] text-text-hi">
          Try again
        </button>
      }
    />
  );
}
