/**
 * The Skeptic's review of a link, read from its trace events (WS3-26). Pure helpers, unit-tested.
 *
 * Event shapes (services/api skeptic.py / pipeline.py, confirmed by nexus-3, 26 Oct):
 * - approve | send_back | drop: input "pair <A>|<B> round <n>", output "score=<x> struck=[...] <critique>";
 *   the pair is always sorted. status approved | needs_revision | rejected.
 * - strike_factor: input "pair <A>|<B> factor <name>", output "fresh=<v> linker=<v>; score <before>→<after>".
 * - recheck_unavailable: input "<A>|<B> <factor> <query>"; the factor stays, marked unverified.
 * - critique_failed: input "<N> pairs round <r>" (whole round; code verdicts stand).
 * - critique_missing: input "<A>|<B>" (the model's reply skipped this pair).
 * The final verdict is link_alerts.skeptic.verdict: at the revision cap a send_back becomes approve or drop
 * without a new event, so the last event is not always the outcome.
 */

import type { Skeptic } from "@/lib/alerts";

// =====================
// Types
// =====================

export type SkepticKind = "approve" | "send_back" | "drop" | "strike" | "unverified" | "critique_failed" | "critique_missing";

export type SkepticStep = {
  seq: number;
  ts: string;
  kind: SkepticKind;
  /** Sorted "A|B", or null for a whole-round event (critique_failed). */
  pair: string | null;
  round: number | null;
  score: number | null;
  struck: string[];
  factor: string | null;
  text: string;
};

export type SkepticEventRow = {
  run_id: string;
  seq: number;
  ts: string;
  action: string;
  input_summary: string | null;
  output_summary: string | null;
  status: string | null;
};

export const SKEPTIC_ACTIONS = ["approve", "send_back", "drop", "strike_factor", "recheck_unavailable", "critique_failed", "critique_missing"] as const;

export const KIND_LABEL: Record<SkepticKind, string> = {
  approve: "Approved", send_back: "Sent back", drop: "Dropped", strike: "Struck a factor",
  unverified: "Could not re-check", critique_failed: "Model critique unavailable", critique_missing: "No model critique for this pair",
};

// =====================
// Parsing
// =====================

/** The trace's pair id for a set of crimes: sorted and joined with "|" (linker.pair_id). */
export function pairKey(crimes: string[]): string {
  return [...crimes].sort().join("|");
}

function parseStruck(s: string): string[] {
  return Array.from(s.matchAll(/'([^']*)'|"([^"]*)"/g), (m) => m[1] ?? m[2]).filter(Boolean);
}

/** One Skeptic trace event as a step, or null when it is not a review step. */
export function parseSkepticEvent(r: SkepticEventRow): SkepticStep | null {
  const input = r.input_summary ?? "";
  const out = (r.output_summary ?? "").trim();
  const base = { seq: r.seq, ts: r.ts, round: null as number | null, score: null as number | null, struck: [] as string[], factor: null as string | null };
  if (r.action === "approve" || r.action === "send_back" || r.action === "drop") {
    const p = /^pair (\S+\|\S+) round (\d+)/.exec(input);
    const o = /^score=([\d.]+)\s+struck=\[([^\]]*)\]\s*([\s\S]*)$/.exec(out);
    return {
      ...base, kind: r.action, pair: p ? p[1] : null, round: p ? Number(p[2]) : null,
      score: o ? Number(o[1]) : null, struck: o ? parseStruck(o[2]) : [], text: o ? o[3].trim() : out,
    };
  }
  if (r.action === "strike_factor") {
    const p = /^pair (\S+\|\S+) factor (\S+)/.exec(input);
    return { ...base, kind: "strike", pair: p ? p[1] : null, factor: p ? p[2] : null, text: out };
  }
  if (r.action === "recheck_unavailable") {
    const p = /^(\S+\|\S+) (\S+)(?: (\S+))?/.exec(input);
    return { ...base, kind: "unverified", pair: p ? p[1] : null, factor: p ? p[2] : null, text: out };
  }
  if (r.action === "critique_failed") {
    const p = /round (\d+)/.exec(input);
    return { ...base, kind: "critique_failed", pair: null, round: p ? Number(p[1]) : null, text: out };
  }
  if (r.action === "critique_missing") {
    const p = /^(\S+\|\S+)$/.exec(input.trim());
    return { ...base, kind: "critique_missing", pair: p ? p[1] : null, text: out };
  }
  return null;
}

// =====================
// Views
// =====================

/** The Skeptic's steps for one alert's pair (plus whole-round critique failures), in trace order. */
export function alertTimeline(rows: SkepticEventRow[], crimes: string[]): SkepticStep[] {
  const key = pairKey(crimes);
  return rows
    .map(parseSkepticEvent)
    .filter((s): s is SkepticStep => s !== null && (s.pair === key || s.pair === null))
    .sort((a, b) => a.seq - b.seq);
}

/** True when the trace ends on a send-back but the alert's verdict differs: the revision cap decided it. */
export function capFlipped(steps: SkepticStep[], skeptic: Skeptic | null): boolean {
  const last = [...steps].reverse().find((s) => s.kind === "approve" || s.kind === "send_back" || s.kind === "drop");
  return !!last && last.kind === "send_back" && !!skeptic && skeptic.verdict !== "needs_revision";
}

/** One-line summary from the alert's own Skeptic record. Says "struck" only when factors were struck. */
export function skepticSummary(s: (Skeptic & { model_critique?: string }) | null): string {
  if (!s) return "No Skeptic record.";
  const verdict = { approved: "approved", needs_revision: "sent back for revision", rejected: "dropped" }[s.verdict] ?? s.verdict;
  const parts = [`Reviewed in ${s.rounds} round${s.rounds === 1 ? "" : "s"}`, `verdict: ${verdict}`];
  if (s.struck.length) parts.push(`struck ${s.struck.join(", ")}`);
  if (s.model_critique === "applied") parts.push("model critique applied");
  else if (s.model_critique === "unavailable") parts.push("model critique unavailable (rule checks only)");
  return parts.join(" · ");
}

export type DroppedLink = { runId: string; ts: string; pair: [string, string]; round: number | null; score: number | null; reason: string };

/** Links the Skeptic dropped (drop events), newest first, one per run and pair. */
export function droppedLinks(rows: SkepticEventRow[]): DroppedLink[] {
  const seen = new Set<string>();
  const out: DroppedLink[] = [];
  for (const r of [...rows].sort((a, b) => b.ts.localeCompare(a.ts) || b.seq - a.seq)) {
    if (r.action !== "drop") continue;
    const s = parseSkepticEvent(r);
    if (!s?.pair) continue;
    const k = `${r.run_id}:${s.pair}`;
    if (seen.has(k)) continue;
    seen.add(k);
    const [a, b] = s.pair.split("|");
    out.push({ runId: r.run_id, ts: r.ts, pair: [a, b], round: s.round, score: s.score, reason: s.text });
  }
  return out;
}
