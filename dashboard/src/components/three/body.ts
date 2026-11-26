/**
 * Procedural human silhouette: points sampled on simple primitives (sphere head, capsule
 * torso and limbs). Generated in code with a seeded PRNG, so nothing is downloaded and the
 * figure is identical on every load.
 */

export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type V3 = [number, number, number];
type Capsule = { a: V3; b: V3; r: number; w: number; sx?: number };

// Standing figure, ~1.78 units tall, centred on x=0, feet at y=0. `sx` widens a part.
const PARTS: Capsule[] = [
  { a: [0, 1.6, 0], b: [0, 1.66, 0.01], r: 0.105, w: 1.2, sx: 0.88 }, // head
  { a: [0, 1.45, 0], b: [0, 1.53, 0], r: 0.05, w: 0.2 }, // neck
  { a: [0, 1.22, 0], b: [0, 1.38, 0], r: 0.16, w: 2.4, sx: 1.45 }, // chest + shoulders
  { a: [0, 0.98, 0], b: [0, 1.2, 0], r: 0.14, w: 1.8, sx: 1.12 }, // waist
  { a: [0, 0.86, 0], b: [0, 0.95, 0], r: 0.155, w: 1.0, sx: 1.25 }, // pelvis
  { a: [-0.27, 1.37, 0], b: [-0.34, 1.07, 0.03], r: 0.05, w: 0.6 }, // upper arms
  { a: [0.27, 1.37, 0], b: [0.34, 1.07, 0.03], r: 0.05, w: 0.6 },
  { a: [-0.34, 1.07, 0.03], b: [-0.38, 0.8, 0.07], r: 0.042, w: 0.5 }, // forearms
  { a: [0.34, 1.07, 0.03], b: [0.38, 0.8, 0.07], r: 0.042, w: 0.5 },
  { a: [-0.385, 0.79, 0.07], b: [-0.39, 0.72, 0.08], r: 0.035, w: 0.12 }, // hands
  { a: [0.385, 0.79, 0.07], b: [0.39, 0.72, 0.08], r: 0.035, w: 0.12 },
  { a: [-0.1, 0.82, 0], b: [-0.12, 0.45, 0.01], r: 0.08, w: 1.2 }, // thighs
  { a: [0.1, 0.82, 0], b: [0.12, 0.45, 0.01], r: 0.08, w: 1.2 },
  { a: [-0.12, 0.45, 0.01], b: [-0.125, 0.07, -0.01], r: 0.058, w: 0.95 }, // shins
  { a: [0.12, 0.45, 0.01], b: [0.125, 0.07, -0.01], r: 0.058, w: 0.95 },
  { a: [-0.125, 0.03, 0.02], b: [-0.125, 0.03, 0.12], r: 0.035, w: 0.15 }, // feet
  { a: [0.125, 0.03, 0.02], b: [0.125, 0.03, 0.12], r: 0.035, w: 0.15 },
];

export interface FigureBuffers {
  base: Float32Array;
  scatter: Float32Array;
  ring: Float32Array;
  seed: Float32Array;
  identity: Float32Array;
}

/** Sample `n` points; `identityShare` of them are identity particles bound for the ring. */
export function buildFigure(n: number, identityShare: number, seed = 1729): FigureBuffers {
  const rnd = mulberry32(seed);
  const total = PARTS.reduce((s, p) => s + p.w, 0);
  const base = new Float32Array(n * 3);
  const scatter = new Float32Array(n * 3);
  const ring = new Float32Array(n * 3);
  const seeds = new Float32Array(n);
  const identity = new Float32Array(n);

  for (let i = 0; i < n; i++) {
    let pick = rnd() * total;
    let part = PARTS[0];
    for (const p of PARTS) {
      pick -= p.w;
      if (pick <= 0) {
        part = p;
        break;
      }
    }
    const t = rnd();
    const cx = part.a[0] + (part.b[0] - part.a[0]) * t;
    const cy = part.a[1] + (part.b[1] - part.a[1]) * t;
    const cz = part.a[2] + (part.b[2] - part.a[2]) * t;
    // point on (slightly inside) the capsule surface
    const u = rnd() * Math.PI * 2;
    const v = Math.acos(2 * rnd() - 1);
    // volume sample biased to the surface: reads as a solid body, no visible columns
    const rr = part.r * Math.pow(rnd(), 0.28);
    base[i * 3] = cx + rr * Math.sin(v) * Math.cos(u) * (part.sx ?? 1);
    base[i * 3 + 1] = cy + rr * Math.cos(v) * 0.92 + (rnd() - 0.5) * 0.004;
    base[i * 3 + 2] = cz + rr * Math.sin(v) * Math.sin(u) * 0.7;

    // far scatter for the formation phase
    const su = rnd() * Math.PI * 2;
    const sv = Math.acos(2 * rnd() - 1);
    const sr = 1.6 + rnd() * 1.6;
    scatter[i * 3] = sr * Math.sin(sv) * Math.cos(su);
    scatter[i * 3 + 1] = 1.0 + sr * Math.cos(sv) * 0.7;
    scatter[i * 3 + 2] = sr * Math.sin(sv) * Math.sin(su);

    // destination on the shield ring (radius 1.15 around the figure's chest)
    const a = rnd() * Math.PI * 2;
    const jitter = (rnd() - 0.5) * 0.06;
    ring[i * 3] = Math.cos(a) * (1.15 + jitter);
    ring[i * 3 + 1] = 1.05 + (rnd() - 0.5) * 0.05;
    ring[i * 3 + 2] = Math.sin(a) * (1.15 + jitter);

    seeds[i] = rnd();
    identity[i] = rnd() < identityShare ? 1 : 0;
  }
  return { base, scatter, ring, seed: seeds, identity };
}
