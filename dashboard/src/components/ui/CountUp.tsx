"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/** Counts up once when visible; renders the final value immediately under reduced motion. */
export function CountUp({ value, digits = 0, suffix = "", delay = 0 }: { value: number; digits?: number; suffix?: string; delay?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setShown(value);
      return;
    }
    const c = animate(0, value, { duration: 1.1, delay, ease: [0.22, 1, 0.36, 1], onUpdate: setShown });
    return () => c.stop();
  }, [inView, reduce, value, delay]);

  return (
    <span ref={ref} className="num">
      {shown.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}
      {suffix}
    </span>
  );
}
