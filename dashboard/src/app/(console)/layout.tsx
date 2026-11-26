import { Suspense } from "react";

import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { listDatasets, listPresets } from "@/lib/server/anamika";
import type { Dataset, Preset } from "@/lib/types";

export const dynamic = "force-dynamic";

/** App shell: atmosphere, glass sidebar, top bar. Screens render inside. */
export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  let datasets: Dataset[] = [];
  let presets: Preset[] = [];
  let offline = false;
  try {
    [datasets, presets] = await Promise.all([listDatasets(), listPresets()]);
  } catch {
    offline = true;
  }
  return (
    <>
      <div className="atmosphere" aria-hidden />
      <div className="relative z-[1] flex min-h-dvh">
        <Suspense>
          <Sidebar />
        </Suspense>
        <div className="flex min-w-0 flex-1 flex-col">
          <Suspense>
            <TopBar datasets={datasets} presets={presets} offline={offline} />
          </Suspense>
          <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
