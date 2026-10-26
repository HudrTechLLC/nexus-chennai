/**
 * Link alerts as the console reads them (spec D3.11, F2, F4; tables from 0002_core).
 * Types plus pure helpers, shared by the inbox, the detail page and the tests.
 * Scores are computed by the pipeline in code; the UI only displays them.
 */

// =====================
// Types (column names match 0002_core)
// =====================

export type AlertStatus = "pending" | "approved" | "rejected";
export type Band = "high" | "medium";

export type EvidenceRef = { view: string; row: string; query?: string; query_id?: string };

export type LinkFactor = {
  alert_id: string;
  factor: FactorName;
  weight: number;
  value: number;
  evidence: EvidenceRef[];
  reason: string;
  struck_by_skeptic: boolean;
};

export type AlertDecision = {
  decision_id: number;
  alert_id: string;
  decision: "approve" | "reject";
  reason_code: ReasonCode | null;
  note: string | null;
  by: string;
  at: string;
  processed_at: string | null;
};

export type MemoryApplied = { memory_id: string; effect: string; text: string };
export type Skeptic = { rounds: number; struck: string[]; verdict: "approved" | "needs_revision" | "rejected" };

export type LinkAlert = {
  alert_id: string;
  kind: "pair" | "series" | "hotspot";
  crimes: string[];
  stations: string[];
  score: number;
  band: Band;
  coverage?: number | null;
  memory_applied: MemoryApplied[];
  skeptic: Skeptic | null;
  rationale: string;
  recommended_action: string | null;
  status: AlertStatus;
  run_id: string | null;
  created_at: string;
  link_factors?: LinkFactor[];
  alert_decisions?: AlertDecision[];
};

// =====================
// Factors (F2)
// =====================

export const FACTORS = [
  "mo_similarity", "space_time", "vehicle", "suspect_description", "weapon_tool",
  "target_profile", "forensic", "corroboration", "offender_return",
] as const;
export type FactorName = (typeof FACTORS)[number];

export const FACTOR_LABEL: Record<FactorName, string> = {
  mo_similarity: "MO similarity",
  space_time: "Space–time",
  vehicle: "Vehicle / ANPR",
  suspect_description: "Suspect description",
  weapon_tool: "Weapon / tool",
  target_profile: "Target profile",
  forensic: "Forensic match",
  corroboration: "Corroboration (tips, 112, news)",
  offender_return: "Offender return",
};

export type FactorRow = LinkFactor & { label: string; contribution: number };

/** Factors in weight order (heaviest first) with their contribution w·v; struck factors contribute 0. */
export function factorRows(factors: LinkFactor[] = []): FactorRow[] {
  return [...factors]
    .sort((a, b) => b.weight - a.weight || a.factor.localeCompare(b.factor))
    .map((f) => ({
      ...f,
      label: FACTOR_LABEL[f.factor] ?? f.factor,
      contribution: f.struck_by_skeptic ? 0 : f.weight * f.value,
    }));
}

/**
 * Share of the total factor weight that had data (D-016). Uses the stored column when the
 * pipeline provides it; otherwise sums the weights of the factor rows present.
 */
export function coverageOf(alert: Pick<LinkAlert, "coverage" | "link_factors">): number {
  if (typeof alert.coverage === "number") return alert.coverage;
  const sum = (alert.link_factors ?? []).reduce((s, f) => s + f.weight, 0);
  return Math.min(1, Math.round(sum * 100) / 100);
}

/** All distinct Zetaris query ids cited by an alert's evidence. */
export function queryIds(factors: LinkFactor[] = []): string[] {
  const ids = new Set<string>();
  for (const f of factors) for (const e of f.evidence ?? []) if (e.query_id) ids.add(e.query_id);
  return Array.from(ids);
}

// =====================
// Decisions (F4)
// =====================

export const REASON_CODES = [
  "different_offenders", "coincidental_location", "already_linked", "data_error",
  "insufficient_evidence", "different_mo", "duplicate_fir", "other",
] as const;
export type ReasonCode = (typeof REASON_CODES)[number];

export const REASON_LABEL: Record<ReasonCode, string> = {
  different_offenders: "Different offenders",
  coincidental_location: "Coincidental location",
  already_linked: "Already linked",
  data_error: "Data error",
  insufficient_evidence: "Insufficient evidence",
  different_mo: "Different MO",
  duplicate_fir: "Duplicate FIR",
  other: "Other",
};

export type DecisionInput = { decision: "approve" | "reject"; reason_code?: string | null; note?: string | null };

/** Returns an error message, or null when the decision may be saved. Mirrors the 0002 check constraint. */
export function validateDecision(d: DecisionInput): string | null {
  if (d.decision !== "approve" && d.decision !== "reject") return "Choose approve or reject.";
  if (d.decision === "reject") {
    if (!d.reason_code) return "A rejection needs a reason.";
    if (!(REASON_CODES as readonly string[]).includes(d.reason_code)) return "Unknown reason.";
    if (d.reason_code === "other" && !d.note?.trim()) return "Say why in the note when the reason is Other.";
  }
  if ((d.note ?? "").length > 2000) return "Keep the note under 2000 characters.";
  return null;
}

/** Most recent decision first, or null. */
export function latestDecision(decisions: AlertDecision[] = []): AlertDecision | null {
  return [...decisions].sort((a, b) => b.at.localeCompare(a.at))[0] ?? null;
}

/**
 * What the officer should see. A decision is written by the console and applied by the worker
 * (H-MEM + status update), so there is a short window where a decision exists but the alert is
 * still pending.
 */
export function decisionState(alert: Pick<LinkAlert, "status" | "alert_decisions">):
  "pending" | "awaiting_worker" | "approved" | "rejected" {
  if (alert.status !== "pending") return alert.status;
  const last = latestDecision(alert.alert_decisions);
  return last && !last.processed_at ? "awaiting_worker" : "pending";
}

// =====================
// Inbox tabs and sorting (G2)
// =====================

export const TABS = ["pending", "approved", "rejected", "mine"] as const;
export type Tab = (typeof TABS)[number];
export const TAB_LABEL: Record<Tab, string> = { pending: "Pending", approved: "Approved", rejected: "Rejected", mine: "Mine" };

export const SORTS = ["score", "newest", "stations"] as const;
export type Sort = (typeof SORTS)[number];

export function parseTab(v: string | undefined): Tab {
  return (TABS as readonly string[]).includes(v ?? "") ? (v as Tab) : "pending";
}
export function parseSort(v: string | undefined): Sort {
  return (SORTS as readonly string[]).includes(v ?? "") ? (v as Sort) : "score";
}

export function sortAlerts<T extends Pick<LinkAlert, "score" | "created_at" | "stations" | "alert_id">>(rows: T[], sort: Sort): T[] {
  const r = [...rows];
  if (sort === "newest") return r.sort((a, b) => b.created_at.localeCompare(a.created_at));
  if (sort === "stations")
    return r.sort((a, b) => b.stations.length - a.stations.length || a.stations.join().localeCompare(b.stations.join()));
  return r.sort((a, b) => b.score - a.score || a.alert_id.localeCompare(b.alert_id));
}

// =====================
// Display helpers
// =====================

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function bandLabel(b: Band): string {
  return b === "high" ? "High" : "Medium";
}
