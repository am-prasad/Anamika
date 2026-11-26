"use client";

import { forceX, forceY } from "d3-force-3d";
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";

import type { Graph } from "@/lib/types";
import { EVIDENCE_COLOR, evidenceGroup } from "./evidence";

type N = { id: number; patient: string | null; file: string; loc: string; x?: number; y?: number };
type L = { source: number | N; target: number | N; type: string };

/**
 * All records as dots, linkage evidence as edges. Linked records sit in teal, unlinked ones in
 * grey; the selected patient is drawn in cyan with its edges coloured by evidence group.
 */
export default function GraphCanvas({
  graph,
  selected,
  pair,
  onSelect,
}: {
  graph: Graph;
  selected: string | null;
  pair: [number, number] | null;
  onSelect: (patient: string | null) => void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const fg = useRef<ForceGraphMethods<N, L> | undefined>(undefined);
  const [size, setSize] = useState({ w: 800, h: 560 });
  const fitted = useRef(false);

  // force-graph mutates its input, so hand it fresh copies
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ id: n.id, patient: n.patient, file: n.file.replace(/^sanitized\//, ""), loc: n.loc })),
      links: graph.edges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
    }),
    // a refresh that returns the same graph must not restart the simulation
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [graph.summary.records, graph.edges.length, graph.nodes[0]?.patient, graph.nodes.at(-1)?.patient],
  );

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const f = fg.current;
    if (!f) return;
    f.d3Force("charge")?.strength?.(-10);
    f.d3Force("link")?.distance?.(10);
    // disconnected clusters would drift apart; a weak pull keeps the whole set in frame
    f.d3Force("x", forceX(0).strength(0.06) as never);
    f.d3Force("y", forceY(0).strength(0.08) as never);
  }, []);

  // fit after the warm-up layout and again once it has settled; the engine-stop event is not
  // reliable while the canvas is still being sized
  useEffect(() => {
    fitted.current = false;
    const timers = [900, 2600].map((ms) => window.setTimeout(() => fg.current?.zoomToFit(500, 64), ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [data]);

  const pairSet = pair ? new Set(pair) : null;

  return (
    <div ref={wrap} className="absolute inset-0">
      <ForceGraph2D<N, L>
        ref={fg}
        graphData={data}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        warmupTicks={160}
        cooldownTime={1200}
        onEngineStop={() => {
          if (!fitted.current) fg.current?.zoomToFit(500, 64);
          fitted.current = true;
        }}
        nodeRelSize={3}
        nodeLabel={(n) => `${n.patient ?? "not linked (null)"} · ${n.file} · ${n.loc}`}
        nodeCanvasObject={(n, ctx, scale) => {
          const on = selected !== null && n.patient === selected;
          const inPair = pairSet?.has(n.id);
          const r = (on || inPair ? 3.6 : 2.4) / Math.max(0.6, Math.sqrt(scale) * 0.8);
          ctx.beginPath();
          ctx.arc(n.x ?? 0, n.y ?? 0, r, 0, Math.PI * 2);
          ctx.shadowBlur = on ? 10 : 0;
          ctx.shadowColor = "rgba(103,232,249,0.8)";
          ctx.fillStyle = on ? "#67E8F9" : n.patient ? "rgba(45,212,191,0.55)" : "rgba(130,150,172,0.55)";
          ctx.fill();
          ctx.shadowBlur = 0;
          if (inPair) {
            ctx.lineWidth = 1.6 / scale;
            ctx.strokeStyle = "#E8F1F8";
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, r + 2.4 / scale, 0, Math.PI * 2);
            ctx.stroke();
          } else if (on) {
            // 2px surface ring keeps overlapping marks apart
            ctx.lineWidth = 1 / scale;
            ctx.strokeStyle = "#0A1424";
            ctx.stroke();
          }
        }}
        nodePointerAreaPaint={(n, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(n.x ?? 0, n.y ?? 0, 6, 0, Math.PI * 2);
          ctx.fill();
        }}
        linkColor={(l) => {
          const s = typeof l.source === "object" ? l.source.patient : null;
          if (selected && s === selected) return EVIDENCE_COLOR[evidenceGroup(l.type)];
          return "rgba(255,255,255,0.07)";
        }}
        linkWidth={(l) => (selected && typeof l.source === "object" && l.source.patient === selected ? 1.6 : 0.6)}
        onRenderFramePost={(ctx, scale) => {
          // the refused link: a dashed line between the two records kept apart
          if (!pair) return;
          const a = data.nodes.find((n) => n.id === pair[0]) as N | undefined;
          const b = data.nodes.find((n) => n.id === pair[1]) as N | undefined;
          if (a?.x === undefined || b?.x === undefined) return;
          ctx.save();
          ctx.setLineDash([4 / scale, 4 / scale]);
          ctx.lineWidth = 1.4 / scale;
          ctx.strokeStyle = "rgba(232,241,248,0.7)";
          ctx.beginPath();
          ctx.moveTo(a.x, a.y ?? 0);
          ctx.lineTo(b.x, b.y ?? 0);
          ctx.stroke();
          ctx.restore();
        }}
        onNodeClick={(n) => onSelect(n.patient)}
        onBackgroundClick={() => onSelect(null)}
        enableNodeDrag={false}
      />
    </div>
  );
}
