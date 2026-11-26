"use client";

import { Info, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/** "Explain this": glass-3 side drawer with the technical detail judges ask about. */
export function ExplainDrawer({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="glass-1 flex h-9 items-center gap-2 rounded-[12px] px-3 text-[13px] font-medium text-text-mid hover:text-text-hi"
        aria-haspopup="dialog"
      >
        <Info size={15} strokeWidth={1.5} /> Explain this
      </button>
      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fixed inset-0 z-40 bg-ink-950/50"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduce ? 0 : 0.18 }}
              onClick={() => setOpen(false)}
            />
            <motion.aside
              role="dialog"
              aria-modal="true"
              aria-label={title}
              className="glass-3 fixed top-0 right-0 z-50 flex h-dvh w-[min(480px,92vw)] flex-col rounded-l-[20px] p-8"
              initial={reduce ? false : { x: 40, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={reduce ? { opacity: 0 } : { x: 40, opacity: 0 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="mb-6 flex items-start justify-between gap-4">
                <div>
                  <p className="label">Explain this</p>
                  <h2 className="mt-1 font-display text-[24px] font-[600] text-text-hi">{title}</h2>
                </div>
                <button ref={closeRef} type="button" onClick={() => setOpen(false)} aria-label="Close" className="rounded-[10px] p-2 text-text-mid hover:bg-glass-2 hover:text-text-hi">
                  <X size={18} strokeWidth={1.5} />
                </button>
              </div>
              <div className="explain-body flex-1 overflow-y-auto pr-2 text-[15px] leading-relaxed text-text-mid">{children}</div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
