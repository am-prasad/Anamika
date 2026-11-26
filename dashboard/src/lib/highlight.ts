import type { Span } from "./types";

/** Segment of rendered text: plain, a detected PII span, a kept clinical span, or an output token. */
export interface Segment {
  text: string;
  kind: "plain" | "removed" | "generalized" | "kept";
  label?: string;
}

/** Clinical values the meaning traps must keep: doses, frequencies, vitals, lab values. */
const CLINICAL = new RegExp(
  [
    String.raw`\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|IU|units|puffs?)\b`,
    String.raw`\b[01]-[01]-[01]\b`,
    String.raw`\b(?:BD|TDS|OD|HS|SOS|QID|STAT|PRN)\b`,
    String.raw`\bBP\s?\d{2,3}/\d{2,3}\b`,
    String.raw`\bSpO2\s?\d{2,3}%?`,
    String.raw`\b(?:Pulse|HR)\s?\d{2,3}(?:/min)?`,
    String.raw`\b\d+(?:\.\d+)?\s?(?:g/dL|mg/dL|mmol/L|/uL)\b`,
    String.raw`\bx\s?\d+\s?(?:days?|wks?|weeks?|months?)\b`,
  ].join("|"),
  "gi",
);

/** Output tokens Anamika writes. */
const TOKENS = /PSN-[0-9A-Z]{6}|\[(?:NAME|RELATIVE|PHONE|EMAIL|AADHAAR|ABHA|PAN|MRN|VOTER_ID|INSURANCE_ID|ADDRESS|VILLAGE|TEHSIL|DISTRICT|DOB|PIN|ICD chapter:[^\]]*)\]|X[0-9A-Z]{6}|\b\d{1,3}-\d{1,3}(?=\s?(?:Yrs?|Y\b|yrs?|years?|वर्ष|\/[MF]))|\b\d{2}\+|\b[1-8]\d{2}\*{3}/g;

function clinicalSpans(text: string): Span[] {
  const out: Span[] = [];
  for (const m of text.matchAll(CLINICAL)) out.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, type: "KEPT" });
  return out;
}

/** Original text → segments from value-free detector spans (+ kept clinical values if asked). */
export function originalSegments(text: string, spans: Span[], kept: Span[], showKept: boolean, dates: { start: number; end: number }[] = []): Segment[] {
  const marks: (Span & { kind: Segment["kind"] })[] = spans.map((s) => ({ ...s, kind: "removed" as const }));
  for (const d of dates) {
    if (!marks.some((m) => d.start < m.end && m.start < d.end)) marks.push({ ...d, type: "DATE", rule: "per-patient shift", kind: "generalized" });
  }
  if (showKept) {
    for (const k of [...kept, ...clinicalSpans(text)]) {
      if (!marks.some((m) => k.start < m.end && m.start < k.end)) marks.push({ ...k, kind: "kept" });
    }
  }
  marks.sort((a, b) => a.start - b.start);
  const out: Segment[] = [];
  let pos = 0;
  for (const m of marks) {
    if (m.start < pos) continue;
    if (m.start > pos) out.push({ text: text.slice(pos, m.start), kind: "plain" });
    out.push({
      text: text.slice(m.start, m.end),
      kind: m.kind,
      label: m.kind === "kept" ? "kept: clinical value or doctor" : m.kind === "generalized" ? "date: moved by this patient's own offset" : `${m.type.toLowerCase().replaceAll("_", " ")} · ${m.rule ?? "rule"}`,
    });
    pos = m.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: "plain" });
  return out;
}

/** Sanitised text → segments: tokens coloured by outcome, kept clinical values optional. */
const DATES = /\b(?:\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[ -](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ -]\d{2,4})\b/g;

export function sanitizedSegments(text: string, showKept: boolean, shifted = false): Segment[] {
  const marks: { start: number; end: number; kind: Segment["kind"]; label: string }[] = [];
  if (shifted) {
    for (const m of text.matchAll(DATES)) marks.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, kind: "generalized", label: "date: shifted, intervals exact" });
  }
  for (const m of text.matchAll(TOKENS)) {
    const t = m[0];
    if (marks.some((k) => (m.index ?? 0) < k.end && k.start < (m.index ?? 0) + t.length)) continue;
    const generalized = /^\d|\*{3}$|\+$|^\[(?:DOB|TEHSIL|DISTRICT|ICD)/.test(t);
    marks.push({
      start: m.index ?? 0,
      end: (m.index ?? 0) + t.length,
      kind: generalized ? "generalized" : "removed",
      label: t.startsWith("PSN-") ? "pseudonym (keyed HMAC)" : generalized ? "generalised" : "removed",
    });
  }
  if (showKept) {
    for (const k of clinicalSpans(text)) {
      if (!marks.some((m) => k.start < m.end && m.start < k.end)) marks.push({ ...k, kind: "kept", label: "kept: clinical value" });
    }
  }
  marks.sort((a, b) => a.start - b.start);
  const out: Segment[] = [];
  let pos = 0;
  for (const m of marks) {
    if (m.start < pos) continue;
    if (m.start > pos) out.push({ text: text.slice(pos, m.start), kind: "plain" });
    out.push({ text: text.slice(m.start, m.end), kind: m.kind, label: m.label });
    pos = m.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), kind: "plain" });
  return out;
}

/** EN / हिंदी / Hinglish chips from the document itself. */
export function languages(text: string): ("EN" | "हिंदी" | "Hinglish")[] {
  const out: ("EN" | "हिंदी" | "Hinglish")[] = [];
  if (/[A-Za-z]{3,}/.test(text)) out.push("EN");
  if (/[ऀ-ॿ]/.test(text)) out.push("हिंदी");
  if (/\b(?:ka|ki|ke|ko|ne|hai|hain|nahi|theek|bukhar|sahab|ji|didi|karo|gaya|gayi)\b/i.test(text)) out.push("Hinglish");
  return out;
}

/** Counts per detected entity type (value-free). */
export function typeCounts(spans: Span[]): [string, number][] {
  const c = new Map<string, number>();
  for (const s of spans) c.set(s.type, (c.get(s.type) ?? 0) + 1);
  return [...c.entries()].sort((a, b) => b[1] - a[1]);
}
