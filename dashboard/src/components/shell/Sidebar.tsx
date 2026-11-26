"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

import { NAV } from "./nav";
import { Wordmark } from "./Wordmark";

/** Slim glass sidebar; collapse state persists per browser. Links keep dataset/preset. */
export function Sidebar() {
  const path = usePathname();
  const params = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(window.localStorage.getItem("anamika.sidebar") === "collapsed");
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      window.localStorage.setItem("anamika.sidebar", c ? "open" : "collapsed");
      return !c;
    });
  };

  const keep = new URLSearchParams();
  for (const k of ["dataset", "preset"]) {
    const v = params.get(k);
    if (v) keep.set(k, v);
  }
  const qs = keep.toString() ? `?${keep}` : "";

  return (
    <aside
      className={cn(
        "glass-1 sticky top-0 z-20 flex h-dvh shrink-0 flex-col border-y-0 border-l-0 px-3 py-5 transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "w-[72px]" : "w-[240px]",
      )}
      aria-label="Console navigation"
    >
      <Link href={`/overview${qs}`} className="mb-8 flex h-10 items-center px-2" aria-label="Anamika home">
        <Wordmark compact={collapsed} />
      </Link>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV.map(({ href, label, short, icon: Icon }, i) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={`${href}${qs}`}
              aria-current={active ? "page" : undefined}
              title={collapsed ? label : undefined}
              className={cn(
                "group relative flex h-11 items-center gap-3 rounded-[12px] px-3 text-[14px] font-medium transition-colors duration-200",
                active ? "bg-glass-2 text-text-hi" : "text-text-mid hover:bg-glass-1 hover:text-text-hi",
              )}
            >
              {active && (
                <span className="absolute top-2.5 bottom-2.5 left-0 w-[2px] rounded-full bg-teal-400 shadow-[0_0_12px_var(--color-teal-glow)]" />
              )}
              <Icon size={18} strokeWidth={1.5} className={active ? "text-teal-400" : "text-text-lo group-hover:text-text-mid"} />
              {!collapsed && (
                <span className="flex flex-1 items-center justify-between">
                  {short}
                  <span className="num font-mono text-[11px] text-text-faint">0{i + 1}</span>
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <button
        type="button"
        onClick={toggle}
        className="flex h-10 items-center gap-2 rounded-[12px] px-3 text-[13px] text-text-lo hover:bg-glass-1 hover:text-text-mid"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight size={16} strokeWidth={1.5} /> : <ChevronLeft size={16} strokeWidth={1.5} />}
        {!collapsed && "Collapse"}
      </button>
    </aside>
  );
}
