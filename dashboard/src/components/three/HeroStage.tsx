"use client";

import { useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { HeroPoster } from "./HeroPoster";

const HeroScene = dynamic(() => import("./HeroScene"), { ssr: false, loading: () => <HeroPoster /> });

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/** Client island: WebGL only when available and on screen; poster otherwise. */
export function HeroStage({ identifiers, replayKey }: { identifiers: number; replayKey: string }) {
  const reduce = useReducedMotion() ?? false;
  const ref = useRef<HTMLDivElement>(null);
  const [webgl, setWebgl] = useState<boolean | null>(null);
  const [visible, setVisible] = useState(true);
  const [tabVisible, setTabVisible] = useState(true);

  useEffect(() => {
    setWebgl(hasWebGL());
    const onVis = () => setTabVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVis);
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 });
    if (ref.current) io.observe(ref.current);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      io.disconnect();
    };
  }, []);

  return (
    <div ref={ref} className="absolute inset-0">
      {webgl === false || webgl === null ? (
        <HeroPoster />
      ) : (
        <HeroScene identifiers={identifiers} replayKey={replayKey} still={reduce} active={visible && tabVisible} />
      )}
    </div>
  );
}
