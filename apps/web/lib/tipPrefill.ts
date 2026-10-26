import type { TipCategory } from "@/lib/tip";

/**
 * /tip/new prefill (WS4-12). Pure functions only, so the server page and the tests share them.
 * A prefill comes from public fields only (the published appeal as `public_appeal` returns it):
 * never a crime_id, an address or a narrative beyond the appeal's own public summary.
 */

// =====================
// Types
// =====================

export const TIP_WHEN = ["", "Morning", "Afternoon", "Evening", "Night"] as const;
export type TipWhen = (typeof TIP_WHEN)[number];

/** What the tip is about, resolved on the server; everything here is already public. */
export type TipSubject = {
  kind: "appeal";
  /** public_incident_id; sent as `appeal` and saved by submit_tip. */
  id: string;
  /** Read-only "About: ..." line. */
  label: string;
  category: TipCategory;
  cell: string | null;
  when: TipWhen;
};

/** The subset of a published appeal the prefill reads (lib/publicData `Appeal`). */
export type PublicAppealFields = {
  id: string; title: string; category: string; area: string; cell: string; week: string; time_window: string;
  summary: string;
};

// =====================
// Field mapping
// =====================

const CELL = /^88[0-9a-f]{13}$/;
const VEHICLE = /two[- ]?wheeler|motor ?(cycle|bike)|scooter|auto[- ]?rickshaw|\b(cab|car|bike|vehicle)s?\b/i;

/** vehicle_seen when the public text says a vehicle was involved; otherwise something_else (chief, WS4-12). */
export function prefillCategory(fields: { category?: string | null; title?: string | null; summary?: string | null }): TipCategory {
  const text = [fields.category, fields.title, fields.summary].filter(Boolean).join(" ").replace(/_/g, " ");
  return VEHICLE.test(text) ? "vehicle_seen" : "something_else";
}

/** "Morning" / "morning" -> "Morning"; anything else -> "" ("Not sure"). */
export function prefillWhen(band: string | null | undefined): TipWhen {
  const b = (band ?? "").trim().toLowerCase();
  return TIP_WHEN.find((w) => w && w.toLowerCase() === b) ?? "";
}

/** Only an H3 resolution-8 cell the form will accept; otherwise no area (the user can pick one). */
export function prefillCell(cell: string | null | undefined): string | null {
  return cell && CELL.test(cell) ? cell : null;
}

export function appealSubject(a: PublicAppealFields): TipSubject {
  return {
    kind: "appeal",
    id: a.id,
    label: [a.title, a.area, a.week].filter(Boolean).join(" · "),
    category: prefillCategory(a),
    cell: prefillCell(a.cell),
    when: prefillWhen(a.time_window),
  };
}

// =====================
// What the form sends
// =====================

/** The text fields of the tip POST. The appeal link is sent only while the subject is still linked. */
export function tipFields(t: {
  category: string; text: string; cell: string | null; appeal: string | null;
  followUp: boolean; code: string | null; passphrase: string | null; pow: string;
}): [string, string][] {
  const out: [string, string][] = [["pow", t.pow], ["category", t.category], ["text", t.text]];
  if (t.cell) out.push(["cell", t.cell]);
  if (t.appeal) out.push(["appeal", t.appeal]);
  if (t.followUp && t.code && t.passphrase) out.push(["follow_up", "1"], ["code", t.code], ["passphrase", t.passphrase]);
  return out;
}
