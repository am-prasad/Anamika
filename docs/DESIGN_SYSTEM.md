# Anamika Console — Design System ("Clinical Glass")

The console is the desk-review and finals face of Anamika. It must read like a product a hospital
CISO would buy: calm, clinical, exact, and quietly spectacular in two places only — the hero scene
and the attack collapse. Everything here is decided before code; deviations need a reason.

## 1. Concept

**Frosted surgical glass over a living data field.** Patients appear only as light and shape, never
as faces or names. The signature moment is *Dissolving Identity*: a human figure made of particles;
the particles that encode identity (name, phone, Aadhaar, village) peel away into a glass shield,
and the figure re-forms as calm teal light. Visible to science, invisible to attackers.

Mood: an operating theatre at night crossed with a security operations centre. It should never read
as "hacker green", never as "cartoon hospital", never as a purple-gradient SaaS template.

## 2. Typography

All fonts are SIL OFL, self-hosted as `woff2` under `dashboard/src/fonts/`, loaded with
`next/font/local`, and exposed as CSS variables on `<html>`. Nothing is fetched at build or run
time; the demo works offline.

| Role | Font | Variable | Why |
|---|---|---|---|
| Display | **Bricolage Grotesque** (variable, wght 200–800, opsz) | `--font-display` | ink-trap grotesque with real character at large sizes; extreme 200/800 contrast for KPIs and the wordmark without looking like a template |
| UI / body | **IBM Plex Sans** (400/500/600) | `--font-sans` | engineered, institutional, excellent at 12–14px, true tabular figures; signals "serious software" not "startup landing page" |
| Data | **IBM Plex Mono** (400/500) | `--font-mono` | pseudonyms (`PSN-7Q2K9D`), SHA prefixes, timings; same family as the UI, so data and labels feel designed together |
| Wordmark (Hindi) | **Tiro Devanagari Hindi** | `--font-deva-display` | calligraphic, literary Devanagari for अनामिका; dignity, not decoration |
| Hindi UI / documents | **Noto Sans Devanagari** (400/500/600) | `--font-deva` | complete conjunct coverage and correct matra shaping for document text in the Redaction Studio |

Scale (px, 1.25 ratio with deliberate jumps):

| Token | Size / line | Font | Use |
|---|---|---|---|
| `kpi-hero` | 88 / 0.95, wght 200, tabular | display | Overview hero numbers (≥ 3× label size) |
| `kpi` | 48 / 1.0, wght 300 | display | KPI tiles |
| `h1` | 40 / 1.1, wght 700 | display | screen titles |
| `h2` | 24 / 1.2, wght 600 | display | section titles |
| `body` | 15 / 1.55 | sans | paragraphs, drawer text |
| `ui` | 14 / 1.4, wght 500 | sans | controls, table cells |
| `label` | 12 / 1.3, wght 600, uppercase, tracking 0.08em | sans | metric labels, column heads |
| `data` | 13 / 1.4, tabular | mono | pseudonyms, hashes, timings |
| `doc` | 14 / 1.7 | mono (Latin) + deva (Devanagari) | document panes |

All metrics use `font-variant-numeric: tabular-nums`.

## 3. Colour tokens

One dark theme. Tokens are CSS variables in `app/globals.css` (`@theme`, Tailwind v4): a single
source of truth.

### Surfaces and text

| Token | Value | Notes |
|---|---|---|
| `--ink-950` | `#050B14` | base background |
| `--ink-900` | `#0A1424` | chart surface, sunken areas |
| `--ink-800` | `#102036` | raised solid (rare) |
| `--glass-1` | `rgba(255,255,255,0.04)` | background tiles |
| `--glass-2` | `rgba(255,255,255,0.07)` | cards |
| `--glass-3` | `rgba(255,255,255,0.11)` | popovers, drawer, modals |
| `--hairline` | `rgba(255,255,255,0.08)` | 1px borders on glass |
| `--text-hi` | `#E8F1F8` | primary text (13.6:1 on cards) |
| `--text-mid` | `#9FB3C8` | secondary text (7.2:1 on cards) |
| `--text-lo` | `#8296AC` | tertiary text (5.1:1 on cards). **Changed from `#5E7389`**, which measured 3.2:1 and fails AA |
| `--text-faint` | `#5E7389` | disabled and decorative only, never for information |

### Semantic accents (UI state, always paired with an icon and a label)

| Token | Value | Meaning | Text use |
|---|---|---|---|
| `--teal-400` | `#2DD4BF` | protected, active, focus, primary action | 8.3:1 on cards |
| `--teal-glow` | `rgba(45,212,191,0.35)` | focus halo, hover glow | — |
| `--cyan-300` | `#67E8F9` | data, links, secondary highlight | 10.7:1 |
| `--amber-400` | `#FBBF24` | generalised (bands, regions, shifted dates) | 9.3:1 |
| `--mint-300` | `#86EFAC` | clinical value deliberately kept | 11.1:1 |
| `--rose-500` | `#F43F5E` | **only** leaks, attack success, errors (marks and borders) | 4.2:1, so not for text |
| `--rose-300` | `#FDA4AF` | rose **text** on glass | 8.2:1 |

Rules: no purple gradients, no white surfaces, no rainbow charts, and rose appears at most once per
screen unless something is actually wrong.

### Chart palette (validated with the dataviz skill's `validate_palette.js`)

The brand accents fail as a categorical set on a dark surface (OKLCH L 0.79–0.87 is outside the dark
band; teal and cyan are only ΔE 9.8 apart for full-colour vision). Charts therefore use the dataviz
documented dark steps, validated against our surface `--ink-900 #0A1424`:

| Slot | Hex | Validation |
|---|---|---|
| 1 blue | `#3987e5` | adjacent (bars, lines, 6 slots): lightness ✓, chroma ✓, CVD worst ΔE 8.4 ✓, normal-vision worst 19.3 ✓, contrast ≥ 3:1 ✓ |
| 2 orange | `#d95926` | all-pairs (scatter, graph nodes): **first 3 slots only**, CVD 9.4 ✓, normal 20.9 ✓ |
| 3 aqua | `#199e70` | |
| 4 yellow | `#c98500` | |
| 5 magenta | `#d55181` | |
| 6 green | `#0ca30c` | |

- **Ordinal / sequential:** one-hue teal ramp `#9ff0e2 → #5fd9c4 → #2bb7a2 → #1a8a7a → #0f5e54`
  (validated: monotone L, ΔL ≥ 0.06, single hue). Used for k-anonymity class sizes and age bands.
- **Before / after** (raw vs Anamika): raw = `--text-lo` slate (recessive), Anamika = teal; always
  direct-labelled.
- **Status:** protected teal, generalised amber, leak rose; each with an icon and a word.
- Text in charts wears text tokens, never the series colour. There is no dual axis anywhere.

## 4. Glass, elevation, radii

| Level | Background | Blur | Border | Shadow | Used for |
|---|---|---|---|---|---|
| glass-1 | `--glass-1` | 12px | hairline | none | grid tiles, table rows on hover |
| glass-2 | `--glass-2` | 18px, saturate 140% | hairline + `inset 0 1px 0 rgba(255,255,255,0.06)` | `0 20px 60px rgba(0,0,0,0.45)` | cards, panes |
| glass-3 | `--glass-3` | 24px, saturate 150% | `rgba(255,255,255,0.12)` | `0 30px 80px rgba(0,0,0,0.55)` | drawer, popovers, command palette |

- Never more than **two** blurred layers on screen at once (the drawer counts as one), and glass is
  never placed over flat colour.
- **Hover (interactive cards):** the border goes to `rgba(45,212,191,0.30)`, the card lifts 2px
  (`translateY(-2px)`) and a `0 0 0 1px var(--teal-glow)` glow appears. No scale.
- **Focus:** a 2px `--teal-400` ring with 2px offset on every focusable element.
- **Radii:** cards 20, inner panels 14, inputs and buttons 12, chips 999, small badges 8.

## 5. Spacing and layout

- 8-pt scale: `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96`.
- 12-column grid, 24px gutters, max content width 1600px, page padding 32px (≥ 1440) / 24px.
- Shell: glass sidebar 240px (collapsed 72px), top bar 64px. One focal point per screen.

## 6. Backgrounds (three layers, always behind glass)

1. `--ink-950` with radial gradients: a teal "operating light" (`#2DD4BF` at 10%, 900px) top-left and
   a faint cyan glow (`#67E8F9` at 6%) bottom-right.
2. A medical grid: 1px lines every 48px at 3% opacity, with a small `+` cross every 4 cells, under a
   radial mask that fades it out at the edges.
3. Grain: an SVG feTurbulence noise layer at 2.5% opacity, static (no animation cost), which kills
   gradient banding.

## 7. Motion tokens

| Token | Value |
|---|---|
| `--ease-out` | `cubic-bezier(0.22, 1, 0.36, 1)` |
| `--dur-fast` / `--dur` / `--dur-slow` | 180 / 240 / 320 ms |
| `--dur-hero` | 1200 ms |
| `--stagger` | 70 ms |
| rise | 12px translate + fade |

Orchestrated moments only:
1. **Load:** background → wordmark → KPI cards rise (70ms stagger) → numbers count up.
2. **Redaction scan:** a 1px teal scanline sweeps the document; PII spans flip to tokens as it passes.
3. **Attack collapse:** the re-identification % falls over 1.2s; histogram bars grow from the baseline.
4. **Identity fusion:** record nodes glide into the PSN node and settle.

Route transitions (`app/template.tsx`) are a 180ms fade plus 8px rise. There are no wobbling springs,
no confetti, and no infinite pulses except the slow "live" status dot. `prefers-reduced-motion`
turns every animation into an instant state change and renders the hero as a still frame.

## 8. The 3D scene — "Dissolving Identity"

- **Stack:** `three` + `@react-three/fiber` + `@react-three/drei` + `@react-three/postprocessing`,
  `next/dynamic(..., { ssr: false, loading: HeroPoster })`.
- **Figure:** about 12k GPU points sampled procedurally from a signed-distance body (sphere head,
  capsule torso, limbs). It is generated in code, so there is no model download. A seeded PRNG makes
  it identical on every load.
- **Particle groups:**
  - identity particles (amber, rose-tinted) make up a share of points proportional to
    `identifiers_detected`, scaled into the 8–15k budget;
  - the clinical particles, the rest of the body, stay put.
- **Timeline** (once on load, and again when a pipeline run finishes):
  - 0–0.6s: points converge into the figure;
  - 0.6–2.2s: identity particles peel off along curl-noise paths into a translucent glass torus;
  - 2.2–3.2s: the figure re-forms in teal;
  - then idle: slow rotation (0.03 rad/s), mouse parallax capped at 6°.
- **Look:** soft bloom (threshold 0.6), exponential fog, a faint DNA-helix ribbon far behind.
  Nothing cartoonish.
- **Performance:**
  - DPR capped at 1.75;
  - `frameloop="demand"` when idle, and the loop pauses on `visibilitychange` or when an
    IntersectionObserver reports the canvas off-screen;
  - point sprites in a single draw call, with the shader doing the animation (no per-frame CPU
    loops over 12k points);
  - target 60 fps on an integrated GPU.
- **Fallbacks:** without WebGL, the scene is replaced by a static SVG poster of the figure
  (`HeroPoster`); with reduced motion, it renders a single re-formed frame.
- **Secondary 3D:** none on the data-dense screens. The Identity Graph stays 2D by default
  (react-force-graph-2d); the 3D toggle is deferred unless it holds 60 fps.

## 9. Components (built once, restyled shadcn/ui primitives, lucide icons at 1.5px stroke)

- `GlassCard` (level 1/2/3, interactive variant)
- `KpiTile`: label, hero number with count-up, delta vs raw, optional sparkline
- `EntityChip`: icon + label per PII type. Colour comes from the *outcome*: teal = removed,
  amber = generalised, mint = kept. Never one hue per type, so there is no rainbow.
- `StatusPill` (live / running / done / failed)
- `Stepper`: Ingest → Detect → Link → Protect → Verify, on a thin ECG baseline that draws as stages
  complete
- `DiffPane`: original | sanitised, with synchronised scroll and span highlights from `/explain`
- `MetricBar`
- `LangChip`: EN / हिंदी / Hinglish, derived from the spans' scripts
- `ExplainDrawer`: a glass-3 side drawer with the technical detail for judges
- `EmptyState`, `Skeleton`, `ErrorState`

## 10. Data flow

- **Browser → Route Handlers → FastAPI.**
  - The browser only calls `dashboard/src/app/api/*/route.ts`.
  - Those handlers call the FastAPI service with a server-only `ANAMIKA_API_URL` and `ANAMIKA_API_KEY`.
- **Decision (conflicts with CLAUDE.md §9 / the brief's `dashboard/server/`).**
  - The FastAPI backend already exists and is tested (`backend/app`, S4). It already runs `main.py`,
    the attacker, the diffs (`/compare`), `/explain` and `/graph`.
  - The console uses it on port 8001 rather than duplicating it in `dashboard/server/`, so there is
    one backend and one security model.
  - `npm run demo` starts both.
- **Live data.**
  - Every screen reads a real job: `POST /jobs/from-dataset` on the synthetic practice set or a fuzz
    set, with `explain`, `utility`, `attack`, `verify_determinism` and `leak_scan`.
  - Compare is enabled with `ANAMIKA_ALLOW_ORIGINALS=true` in demo mode only.
  - A full attack run takes about 2 minutes. The console therefore starts one job per preset at launch
    (still live pipeline output), and the Attack Simulator switches between their results instantly.
    "Re-run" triggers a fresh job.
- **URL state:** `?dataset=practice&preset=balanced&job=<id>&doc=<key>`, so demo states are
  shareable. SWR polls job status.

## 11. Screens (ASCII wireframes, 1440×900)

Shell (all screens)

```
┌──────────┬───────────────────────────────────────────────────────────────────────────┐
│ ◆ ANAMIKA│ अनामिका   Dataset[practice ▾]  Preset[Balanced ▾]  ● live   [ Run pipeline ]│
│ अनामिका  ├───────────────────────────────────────────────────────────────────────────┤
│          │                                                                           │
│ ◎ Overview│                       (screen content, 12-col)                          │
│ ▤ Redact. │                                                                           │
│ ⟁ Identity│                                                                           │
│ ⚔ Attack  │                                                                           │
│ ✚ Clinical│                                                                           │
│ ⛨ Audit   │                                                                           │
│          │                                                                           │
│ ‹ collapse│                                                                           │
└──────────┴───────────────────────────────────────────────────────────────────────────┘
```

1. Command Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Command Overview                                         [Explain this ›]            │
│ 200 files from 4 hospitals, cleaned in 2.5 s. Nothing identifying left.              │
│ ┌───────────────────────────────────────────────┐ ┌──────────────┐ ┌──────────────┐  │
│ │                                               │ │ RE-ID RISK   │ │ IDENTIFIERS  │  │
│ │        [ 3D: Dissolving Identity ]            │ │ 98% → 2%     │ │ 3,268        │  │
│ │        figure + glass shield ring             │ │ ▁▂▃▅ vs raw  │ │ removed      │  │
│ │                                               │ └──────────────┘ └──────────────┘  │
│ │                                               │ ┌──────────────┐ ┌──────────────┐  │
│ │                                               │ │ PATIENTS     │ │ CANARY LEAKS │  │
│ └───────────────────────────────────────────────┘ │ 48 linked    │ │ 0            │  │
│ Ingest ─╱╲─ Detect ─╱╲─ Link ─╱╲─ Protect ─╱╲─ Verify   └──────────────┘ └──────────────┘ │
│ ┌ Clinical kept 98.1% ┐ ┌ Runtime 2.5s / 900s ┐ ┌ Peak RAM 41 / 4096 MB ┐ ┌ Quarantined 7 ┐│
└──────────────────────────────────────────────────────────────────────────────────────┘
```

2. Redaction Studio

```
┌ Redaction Studio ─ one document, before and after ─────────── [EN][हिंदी][Hinglish] ┐
│ Files ▾ (search)   │ ORIGINAL (synthetic)          │ ANAMIKA                        │
│ ▸ notes/…          │ Name: ▓▓▓▓▓▓ ▓▓▓▓▓            │ Name: PSN-7Q2K9D               │
│ ▸ prescriptions/…  │ Mob: ▓▓▓▓▓ ▓▓▓▓▓              │ Mob: [PHONE]                   │
│ ▸ discharge/…      │ ▓▓▓▓ sahab ka BP 117/82       │ [NAME] ka BP 117/82  (mint)    │
│                    │ ───── teal scanline ─────     │                                │
│                    ├───────────────────────────────┴────────────────────────────────┤
│                    │ Found: [NAME 3][PHONE 1][MRN 2]  Kept: [dose][vital][doctor]  ☐ show kept │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

3. Identity Graph

```
┌ Identity Graph ─ 877 records → 48 people, 0 wrong merges ─────────────────────────────┐
│ ┌───────────────────────────────────────────────┐ ┌ Selected: PSN-7Q2K9D ──────────┐ │
│ │   ○ reg   ○ opd  ○ rx(हिं)                    │ │ 14 records · 3 hospitals        │ │
│ │      ╲     │    ╱                             │ │ hospital_id ×9, phone ×3,       │ │
│ │        ◉ PSN-7Q2K9D                           │ │ name+village+age ×1             │ │
│ │      ╱         ╲                              │ ├ Kept apart ─────────────────────┤ │
│ │   ○ lab        ○ note                         │ │ same name, different age        │ │
│ └───────────────────────────────────────────────┘ │ FS score 8.3 < 12 → not merged  │ │
│ legend: hospital (3 slots) · evidence type        └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

4. Attack Simulator

```
┌ Attack Simulator ─ the organisers' attack, run on raw and on our release ────────────┐
│ Preset: Research ──●──────── Balanced ─────── Strict                                 │
│ ┌ Patients re-identified ─────────────┐ ┌ Risk by attack (vs raw = 1.0) ─────────────┐│
│ │   98%  →  2%                        │ │ A1 direct     ▏                             ││
│ │   raw     Anamika                   │ │ A2/3 registry ▍                             ││
│ └─────────────────────────────────────┘ │ A4 profile    ▏                             ││
│ ┌ Candidates left per patient (k) ────┐ │ A5 targeted   ███▌                          ││
│ │ ▁ ▃ ▅ █ ▆   k=1 … k≥5               │ │ A6/A7         ·                             ││
│ └─────────────────────────────────────┘ └────────────────────────────────────────────┘│
│ Utility kept: 98.1%   Resistance 0.914 (≈ 22.8/25)                    [Re-run attack] │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

5. Clinical Integrity

```
┌ Clinical Integrity ─ every dose, lab and stay length survives ───────────────────────┐
│ ┌ Probes kept by kind ───────────────┐ ┌ Length of stay: before vs after ───────────┐ │
│ │ medication ████████████ 100%       │ │       ·  ·                                  │ │
│ │ dose       ████████████ 100%       │ │    ·  ·   (all on the diagonal)            │ │
│ │ lab        ████████████ 100%       │ │  ·                                          │ │
│ │ district   ▓▓▓▓▓▓▓      generalised│ └─────────────────────────────────────────────┘ │
│ └────────────────────────────────────┘ ┌ Age bands truthful 100% ┐ ┌ Retention 97.4% ┐│
└──────────────────────────────────────────────────────────────────────────────────────┘
```

6. Security & Audit

```
┌ Security & Audit ─ prove it: determinism, rotation, zero leaks ──────────────────────┐
│ ┌ Leak scan ───────┐ ┌ Determinism ──────────┐ ┌ Secret rotation ─────────────────┐ │
│ │ 0 / 3,230        │ │ 194/194 identical     │ │ 0 / 53 pseudonyms reused         │ │
│ │ canaries 0 / 4   │ │ sha256 a3f…  = a3f…   │ │ 186 files changed                │ │
│ └──────────────────┘ └───────────────────────┘ └──────────────────────────────────┘ │
│ ┌ Quarantine (7) ──────────────────────────┐ ┌ Design: keys away from data ───────┐ │
│ │ sha 15f3… json_too_deep                  │ │ secret → HKDF → pseudo/shift/enc   │ │
│ │ sha e3b0… empty_file  …                  │ │ PII-free logs · AES-GCM temp       │ │
│ └──────────────────────────────────────────┘ └────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

## 12. Copy and content rules

- Short, specific, human; real numbers from the run. Each screen gets an H1 plus one line of what
  it proves.
- Banned words: unlock, empower, seamless, revolutionize, cutting-edge, leverage, "in today's world";
  no lorem ipsum, no fake logos, testimonials or avatars, no emojis.
- Real-looking PII appears only in the Redaction Studio's *original* pane, from synthetic data, in
  demo mode.

## 13. Quality bar per screen

Each screen must pass all of these before it is done:
- screenshots at 1440×900 and 1920×1080;
- Devanagari checked;
- no console errors and no hydration warnings;
- a first paint under 1.5s on `next start`;
- keyboard navigation and visible focus;
- reduced motion;
- an `unslop` copy pass and an `impeccable`-style critique pass.
