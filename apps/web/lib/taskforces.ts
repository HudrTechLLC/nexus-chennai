/**
 * Joint task forces as the console reads them (spec G2 /console/taskforces, LNK-09, A4; 0004_06_03).
 * Pure types and helpers. Who may do what mirrors the RPCs in 0004_06_03 exactly; the database is
 * the gate (NFR-07), these helpers only decide which buttons to show.
 */

import type { Role } from "@/lib/roles";

// =====================
// Types (column names match 0002 + 0004_06_03)
// =====================

export const TF_STATUSES = ["proposed", "active", "closed", "declined"] as const;
export type TfStatus = (typeof TF_STATUSES)[number];

export type Taskforce = {
  taskforce_id: string;
  name: string;
  purpose: string | null;
  series_id: string | null;
  alert_id: string | null;
  status: TfStatus;
  created_by: string | null;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  closed_at: string | null;
  synthetic: boolean;
};

export type TfMember = { taskforce_id: string; user_id: string; role: "lead" | "member"; added_by: string | null; added_at: string };
export type TfCase = { taskforce_id: string; crime_id: string; added_by: string | null; added_at: string };
export type TfNote = { note_id: number; taskforce_id: string; author: string; kind: "note" | "decision"; text: string; at: string };

export const STATUS_LABEL: Record<TfStatus, string> = { proposed: "Proposed", active: "Active", closed: "Closed", declined: "Declined" };

export function isTfStatus(v: unknown): v is TfStatus {
  return typeof v === "string" && (TF_STATUSES as readonly string[]).includes(v);
}

// =====================
// Permissions (mirror 0004_06_03)
// =====================

const SUPER: Role[] = ["supervisor", "admin"];

export type TfAbilities = {
  approve: boolean; // proposed → active / declined
  close: boolean; // active → closed
  manageMembers: boolean;
  addNote: boolean;
  linkCases: boolean;
};

/** What this officer may do on this task force. */
export function abilities(role: Role, status: TfStatus, membership: "lead" | "member" | null): TfAbilities {
  const sup = SUPER.includes(role);
  const open = status === "proposed" || status === "active";
  return {
    approve: sup && status === "proposed",
    close: sup && status === "active",
    manageMembers: sup && open,
    addNote: open && (sup || membership !== null),
    linkCases: open && (sup || membership === "lead"),
  };
}

/** Who may propose a task force (taskforce_propose). */
export function canPropose(role: Role | null | undefined): boolean {
  return role === "analyst" || role === "supervisor" || role === "admin";
}

// =====================
// Input checks (same limits as the RPCs, so the form explains them before the database refuses)
// =====================

export function validateProposal(input: { name: string; purpose?: string }): string | null {
  const name = input.name.trim();
  if (name.length < 3 || name.length > 120) return "Give the task force a name of 3–120 characters.";
  if ((input.purpose ?? "").length > 2000) return "Keep the purpose under 2000 characters.";
  return null;
}

export function validateNote(text: string): string | null {
  const t = text.trim();
  if (!t) return "Write a note first.";
  if (t.length > 2000) return "Notes are limited to 2000 characters.";
  return null;
}

/** Crime ids from a free-text box: split on commas, spaces or new lines, upper-cased, de-duplicated. */
export function parseCrimeIds(raw: string): string[] {
  return Array.from(new Set(raw.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter((s) => /^[A-Z0-9-]{6,40}$/.test(s))));
}

/** A default name for a proposal from a series or alert, e.g. "Joint task force · Red Pulsar snatchings". */
export function suggestedName(source: { seriesName?: string | null; alertId?: string | null }): string {
  if (source.seriesName) return `Joint task force · ${source.seriesName}`.slice(0, 120);
  if (source.alertId) return `Joint task force · ${source.alertId}`;
  return "";
}

// =====================
// Display helpers
// =====================

/** Counts per status for the list tabs and DASH-07 (active = "joint task forces"). */
export function countByStatus(rows: Pick<Taskforce, "status">[]): Record<TfStatus | "all", number> {
  const out = { all: rows.length, proposed: 0, active: 0, closed: 0, declined: 0 };
  for (const r of rows) if (isTfStatus(r.status)) out[r.status]++;
  return out;
}

/** Leads first, then members, each by name. */
export function sortMembers<T extends { role: "lead" | "member"; name: string }>(rows: T[]): T[] {
  return rows.slice().sort((a, b) => (a.role === b.role ? a.name.localeCompare(b.name) : a.role === "lead" ? -1 : 1));
}

/** Stations spanned by the linked cases (from their briefs), for the "joint" label. */
export function stationsSpanned(briefs: { station_id: string }[]): string[] {
  return Array.from(new Set(briefs.map((b) => b.station_id).filter(Boolean))).sort();
}
