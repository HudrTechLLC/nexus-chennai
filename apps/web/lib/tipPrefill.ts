import type { TipCategory } from "@/lib/tip";

/**
 * /tip/new prefill (WS4-12). Pure functions only, so the server page and the tests share them.
 * A prefill comes from public fields only (the published appeal as `public_appeal` returns it, or the
 * public crime card as `public_crime` returns it): never a crime_id, an address or a narrative beyond
 * the appeal's own public summary or the card's MO summary.
 */

// =====================
// Types
// =====================

export const TIP_WHEN = ["", "Morning", "Afternoon", "Evening", "Night"] as const;
export type TipWhen = (typeof TIP_WHEN)[number];

/** What the tip is about, resolved on the server; everything here is already public. */
export type TipSubject = {
  /** appeal: public_incident_id, sent as `appeal`. about: public crime-card id (PC-...), sent as `about`. */
  kind: "appeal" | "about";
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

/** The subset of a public crime card the prefill reads (0007_11 public_crime; nexus-5's CrimeCard). */
export type CrimeCardFields = {
  public_id: string; category: string; sub_type: string | null; week: string; time_window: string;
  cell: string; area: string | null; mo_summary: string | null;
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

const VEHICLE_SUB_TYPES = new Set(["two_wheeler_theft", "car_theft"]);

/** "chain_snatching" -> "Chain snatching". */
const labelOf = (slug: string) => slug.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());

/** "2026-W42" -> "week 42". */
const weekShort = (week: string) => {
  const m = /^\d{4}-W(\d{2})$/.exec(week);
  return m ? `week ${Number(m[1])}` : week;
};

export function appealSubject(a: PublicAppealFields): TipSubject {
  return {
    kind: "appeal",
    id: a.id,
    label: [a.title, a.area, weekShort(a.week)].filter(Boolean).join(" · "),
    category: prefillCategory(a),
    cell: prefillCell(a.cell),
    when: prefillWhen(a.time_window),
  };
}

/**
 * A crime card's prefill (chief, WS4-12): vehicle_seen for vehicle sub-types or an MO summary naming a
 * vehicle, else something_else; label "<Category> · <sub-type> · <area> · week <NN>".
 */
export function crimeSubject(c: CrimeCardFields): TipSubject {
  const vehicle = (c.sub_type !== null && VEHICLE_SUB_TYPES.has(c.sub_type))
    || prefillCategory({ category: c.category, title: c.sub_type, summary: c.mo_summary }) === "vehicle_seen";
  const sub = c.sub_type && c.sub_type !== c.category ? labelOf(c.sub_type) : null;
  return {
    kind: "about",
    id: c.public_id,
    label: [labelOf(c.category), sub, c.area, weekShort(c.week)].filter(Boolean).join(" · "),
    category: vehicle ? "vehicle_seen" : "something_else",
    cell: prefillCell(c.cell),
    when: prefillWhen(c.time_window),
  };
}

// =====================
// What the form sends
// =====================

/** The text fields of the tip POST. A link (appeal or crime card) is sent only while it is still linked. */
export function tipFields(t: {
  category: string; text: string; cell: string | null; appeal: string | null; about?: string | null;
  followUp: boolean; code: string | null; passphrase: string | null; pow: string;
}): [string, string][] {
  const out: [string, string][] = [["pow", t.pow], ["category", t.category], ["text", t.text]];
  if (t.cell) out.push(["cell", t.cell]);
  if (t.appeal) out.push(["appeal", t.appeal]);
  if (t.about) out.push(["about", t.about]);
  if (t.followUp && t.code && t.passphrase) out.push(["follow_up", "1"], ["code", t.code], ["passphrase", t.passphrase]);
  return out;
}
