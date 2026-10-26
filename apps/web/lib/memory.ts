/**
 * H-MEM as the console reads it (spec E4, G2 /console/memory; tables from 0005, D-020).
 * Pure helpers that join three things into "how an analyst decision changed later scores":
 *   alert_decisions → hmem_memories (alert_id, decision, reason) → hmem_ledger (confidence over time)
 *   → later link_alerts whose memory_applied[] names the memory (hmem_effects(), 0004_06_02).
 * The engine computes every number; the console only displays and sums what it recorded.
 */

// =====================
// Types (column names match 0005_01)
// =====================

export type Layer = "short_term" | "working" | "long_term";

export type MemoryRow = {
  id: string; // '<store>:mem-N'
  store: string;
  memory_id: string; // 'mem-N', what link_alerts.memory_applied[] carries
  content: string;
  tags: string[];
  confidence: number;
  layer: Layer;
  decision: string | null;
  polarity: -1 | 0 | 1 | null;
  reason_code: string | null;
  alert_id: string | null;
  note: string | null;
  synthetic: boolean;
  created_at: string;
  updated_at: string;
};

export type LedgerRow = {
  id: number;
  store: string;
  memory_id: string;
  action: string;
  actor: string;
  at: string;
  details: { previousState?: { confidence?: number; layer?: string }; newState?: { confidence?: number; layer?: string }; details?: Record<string, unknown> } | null;
  entry_hash: string;
  synthetic: boolean;
};

/** One (alert, memory) application from hmem_effects(). */
export type Effect = {
  alert_id: string;
  memory_id: string;
  effect: string | null; // "+0.03", the whole adjustment the alert recorded
  text: string | null;
  score: number;
  band: "high" | "medium";
  status: "pending" | "approved" | "rejected";
  kind: string;
  crimes: string[];
  stations: string[];
  created_at: string;
};

export type ConfidencePoint = { at: string; action: string; confidence: number };

export type MemoryStory = {
  memory: MemoryRow;
  history: ConfidencePoint[]; // create + every confidence change, in time order
  applied: (Effect & { delta: number | null; shared: number })[]; // later alerts it adjusted, oldest first
  raised: number; // later alerts it pushed up
  lowered: number; // later alerts it pushed down
};

// =====================
// Helpers
// =====================

export const LAYER_LABEL: Record<Layer, string> = { short_term: "Short term", working: "Working", long_term: "Long term" };

/** Ledger actions as analysts read them. Unknown actions keep their engine name. */
export const ACTION_LABEL: Record<string, string> = {
  create: "Memory created", read: "Retrieved for a pair", update: "Updated", delete: "Deleted",
  feedback: "Feedback", promote: "Promoted", demote: "Demoted", merge: "Merged",
  conflict_detected: "Conflict found", conflict_resolved: "Conflict resolved",
  sleep_consolidate: "Consolidated", sleep_archive: "Archived", sleep_synthesize: "Synthesised",
  dream_proposed: "Insight proposed", dream_approved: "Insight approved", dream_rejected: "Insight rejected", restore: "Restored",
};

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action.replace(/_/g, " ");
}

/** "+0.03" → 0.03; anything unparsable → null. */
export function parseEffect(effect: string | null | undefined): number | null {
  if (effect == null) return null;
  const cleaned = String(effect).replace(/[^\d.+-]/g, "");
  if (!/\d/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** Confidence before and after a ledger entry, when the engine recorded both states. */
export function confidenceChange(e: Pick<LedgerRow, "details">): { before: number | null; after: number | null } {
  const before = e.details?.previousState?.confidence;
  const after = e.details?.newState?.confidence;
  return { before: typeof before === "number" ? before : null, after: typeof after === "number" ? after : null };
}

/** "approve" → "Approved", "reject" → "Rejected". */
export function decisionLabel(d: string | null): string {
  if (!d) return "—";
  const k = d.toLowerCase();
  if (k.startsWith("approv")) return "Approved";
  if (k.startsWith("reject")) return "Rejected";
  return d;
}

/**
 * Joins memories, their ledger and the later alerts they adjusted into one story per memory.
 * A memory matches an effect by memory_id; when several stores hold the same memory_id the
 * `preferStore` copy wins. `shared` is how many memories split one adjustment: the alert records
 * one effect per adjustment, so a memory's own share is unknown and the full effect is shown.
 */
export function memoryStories(memories: MemoryRow[], effects: Effect[], ledger: LedgerRow[], preferStore = "nexus"): MemoryStory[] {
  const byMid = new Map<string, MemoryRow>();
  for (const m of memories) {
    const cur = byMid.get(m.memory_id);
    if (!cur || (m.store === preferStore && cur.store !== preferStore)) byMid.set(m.memory_id, m);
  }

  const perAdjustment = new Map<string, number>(); // alert_id|effect|text → memories sharing it
  for (const e of effects) {
    const k = `${e.alert_id}|${e.effect}|${e.text}`;
    perAdjustment.set(k, (perAdjustment.get(k) ?? 0) + 1);
  }

  const stories = new Map<string, MemoryStory>();
  for (const m of Array.from(byMid.values())) stories.set(m.id, { memory: m, history: [], applied: [], raised: 0, lowered: 0 });

  for (const e of ledger.slice().sort((a, b) => a.at.localeCompare(b.at) || a.id - b.id)) {
    const m = byMid.get(e.memory_id);
    if (!m || m.store !== e.store) continue;
    const { after } = confidenceChange(e);
    if (after == null) continue;
    const s = stories.get(m.id)!;
    const last = s.history[s.history.length - 1];
    if (!last || last.confidence !== after || e.action === "create") s.history.push({ at: e.at, action: e.action, confidence: after });
  }

  for (const e of effects.slice().sort((a, b) => a.created_at.localeCompare(b.created_at))) {
    const m = byMid.get(e.memory_id);
    if (!m) continue;
    // Only alerts after the memory existed count as "later" (a memory never changes the alert it came from).
    if (m.alert_id && e.alert_id === m.alert_id) continue;
    const s = stories.get(m.id)!;
    const delta = parseEffect(e.effect);
    s.applied.push({ ...e, delta, shared: perAdjustment.get(`${e.alert_id}|${e.effect}|${e.text}`) ?? 1 });
    if (delta != null && delta > 0) s.raised++;
    if (delta != null && delta < 0) s.lowered++;
  }

  return Array.from(stories.values()).sort((a, b) =>
    b.applied.length - a.applied.length || b.memory.updated_at.localeCompare(a.memory.updated_at) || a.memory.id.localeCompare(b.memory.id));
}

export type MemorySummary = {
  memories: number;
  approved: number;
  rejected: number;
  byLayer: Record<Layer, number>;
  meanConfidence: number | null;
  alertsAdjusted: number;
  raised: number;
  lowered: number;
};

/** Headline numbers for the page. An alert adjusted by several memories counts once. */
export function summarise(memories: MemoryRow[], effects: Effect[]): MemorySummary {
  const byLayer: Record<Layer, number> = { short_term: 0, working: 0, long_term: 0 };
  let approved = 0;
  let rejected = 0;
  let sum = 0;
  for (const m of memories) {
    if (m.layer in byLayer) byLayer[m.layer]++;
    if (decisionLabel(m.decision) === "Approved") approved++;
    if (decisionLabel(m.decision) === "Rejected") rejected++;
    sum += Number(m.confidence);
  }
  const perAlert = new Map<string, number | null>();
  for (const e of effects) if (!perAlert.has(e.alert_id)) perAlert.set(e.alert_id, parseEffect(e.effect));
  let raised = 0;
  let lowered = 0;
  perAlert.forEach((d) => {
    if (d != null && d > 0) raised++;
    if (d != null && d < 0) lowered++;
  });
  return {
    memories: memories.length, approved, rejected, byLayer,
    meanConfidence: memories.length ? sum / memories.length : null,
    alertsAdjusted: perAlert.size, raised, lowered,
  };
}

/** The score the alert would have had without H-MEM (its recorded score minus the recorded effect). */
export function scoreBeforeMemory(score: number, delta: number | null): number | null {
  if (delta == null) return null;
  return Math.max(0, Math.min(1, Math.round((score - delta) * 1000) / 1000));
}

/** Ledger filter from the URL: "decisions" hides the high-volume "read" entries (default). */
export type LedgerFilter = "decisions" | "all" | string;

export function parseLedgerFilter(raw: string | undefined): LedgerFilter {
  if (!raw || raw === "decisions") return "decisions";
  if (raw === "all" || raw in ACTION_LABEL) return raw;
  return "decisions";
}
