"use client";

import { MotionConfig } from "motion/react";

/**
 * Route transition: 180ms fade + 8px rise, as a CSS animation so content is visible even
 * before hydration (no server-rendered opacity: 0). The global reduced-motion rule makes it instant.
 */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <div className="animate-[route_180ms_var(--ease-clinical)_both]">{children}</div>
    </MotionConfig>
  );
}
