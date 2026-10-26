/**
 * Tips as the console reads them (spec D3.6, G2 /console/tips; tables from 0002 + 0004_04).
 * Tip text is untrusted: it is only ever shown as plain text, never interpreted.
 */

export type TipStatus = "new" | "screened" | "quarantined" | "urgent" | "reviewed" | "closed";

export type Guard = {
  verdict?: string; injection?: boolean; spam_score?: number; threat?: boolean;
  route?: string; intent?: string; risk?: string[]; action?: "clean" | "quarantine" | "urgent";
} | null;

export type TipRow = {
  tip_id: string;
  public_incident_id: string | null;
  channel: string;
  category: string;
  text: string;
  follow_up_enabled: boolean;
  guard: Guard;
  approx_cell: string | null;
  received_week: string;
  status: TipStatus;
  synthetic: boolean;
  tip_media?: { media_id: string; kind: string; path: string; faces_blurred: boolean }[];
  tip_reviews?: { review_id: number; useful: boolean; crime_id: string | null; note: string | null; by: string; at: string }[];
};

export const TIP_TABS = ["triage", "urgent", "quarantined", "reviewed", "all"] as const;
export type TipTab = (typeof TIP_TABS)[number];
export const TIP_TAB_LABEL: Record<TipTab, string> = {
  triage: "To triage", urgent: "Urgent", quarantined: "Quarantined", reviewed: "Reviewed", all: "All",
};

/** Status filter for a tab. "To triage" = new + screened (not yet reviewed, not quarantined). */
export function statusesFor(tab: TipTab): TipStatus[] | null {
  switch (tab) {
    case "triage": return ["new", "screened"];
    case "urgent": return ["urgent"];
    case "quarantined": return ["quarantined"];
    case "reviewed": return ["reviewed", "closed"];
    default: return null;
  }
}

export function parseTipTab(v: string | undefined): TipTab {
  return (TIP_TABS as readonly string[]).includes(v ?? "") ? (v as TipTab) : "triage";
}

export type GuardBadge = { label: string; tone: "ok" | "warn" | "bad" | "muted" };

/** Human summary of the Tip Guard / Scout Intent result. Null guard = not screened yet. */
export function guardBadges(g: Guard, status: TipStatus): GuardBadge[] {
  if (!g) return [{ label: status === "new" ? "Not screened yet" : "No screening record", tone: "muted" }];
  const out: GuardBadge[] = [];
  const action = g.action ?? (g.verdict === "clean" ? "clean" : g.verdict === "quarantine" || g.verdict === "quarantined" ? "quarantine" : g.verdict === "urgent" ? "urgent" : undefined);
  if (action === "clean") out.push({ label: "Guard: clean", tone: "ok" });
  if (action === "quarantine") out.push({ label: "Guard: quarantined", tone: "bad" });
  if (action === "urgent") out.push({ label: "Guard: urgent", tone: "warn" });
  if (g.injection) out.push({ label: "Prompt-injection attempt", tone: "bad" });
  if (g.threat) out.push({ label: "Threat language", tone: "bad" });
  if (typeof g.spam_score === "number") out.push({ label: `Spam ${Math.round(g.spam_score * 100)}%`, tone: g.spam_score >= 0.5 ? "warn" : "muted" });
  for (const r of g.risk ?? []) out.push({ label: r.replaceAll("_", " "), tone: "warn" });
  if (g.intent) out.push({ label: `Intent: ${g.intent.replaceAll("_", " ")}`, tone: "muted" });
  return out.length ? out : [{ label: `Guard: ${g.verdict ?? "unknown"}`, tone: "muted" }];
}

export const TIP_CATEGORY_LABEL: Record<string, string> = {
  vehicle_seen: "Vehicle seen", person_seen: "Person seen", have_cctv: "Has CCTV",
  item_for_sale: "Stolen item for sale", something_else: "Something else",
};

export function validateReview(input: { useful: unknown; note?: string | null }): string | null {
  if (typeof input.useful !== "boolean") return "Mark the tip useful or not useful.";
  if ((input.note ?? "").length > 2000) return "Keep the note under 2000 characters.";
  return null;
}

export function validatePoliceReply(text: string, followUp: boolean): string | null {
  if (!followUp) return "This tipster chose full anonymity, so there is no way to reply.";
  const t = text.trim();
  if (t.length < 2) return "Write a reply.";
  if (t.length > 2000) return "Keep the reply under 2000 characters.";
  return null;
}
