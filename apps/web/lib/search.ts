/**
 * Console search (spec G2 /console/search, B4): one box plus facets.
 * Pure parsing and classification; data access is in lib/searchData.ts.
 */
import { normaliseFir, normalisePlate, parseCaseFilters, type CaseFilters } from "@/lib/cases";

export type QueryKind = "empty" | "crime_id" | "fir" | "plate" | "text";

export type ParsedSearch = {
  q: string;
  kind: QueryKind;
  /** The normalised value the kind matched (FIR "1182/2026", plate "TN09??4471", id), or the free text. */
  value: string;
  /** Free-text words for narrative / name / tip matching (ILIKE, all must match). */
  words: string[];
  facets: Pick<CaseFilters, "station" | "category" | "status" | "from" | "to">;
};

/** Tip statuses search may show. Unscreened and quarantined tips stay in triage only (R8). */
export const SEARCHABLE_TIP_STATUSES = ["screened", "urgent", "reviewed", "closed"] as const;

const CRIME_ID_RE = /^[A-Z]{2,5}-[A-Z0-9]{1,4}-\d{4}-\d{1,6}$/;
const PLATE_HINT_RE = /^[A-Z]{2}\s?\d{1,2}/;

/** Decides what a typed query is: a case id, an FIR number, a plate fragment, or words. */
export function classifyQuery(raw: string): { kind: QueryKind; value: string } {
  const q = raw.trim();
  if (!q) return { kind: "empty", value: "" };
  const up = q.toUpperCase();
  if (CRIME_ID_RE.test(up)) return { kind: "crime_id", value: up };
  const fir = normaliseFir(q.replace(/^fir\s*(no\.?)?\s*/i, ""));
  if (fir && (fir.includes("/") || /^fir/i.test(q))) return { kind: "fir", value: fir };
  const plate = normalisePlate(q);
  if (plate && (q.includes("?") || q.includes("*") || PLATE_HINT_RE.test(up) || /^\d{4}$/.test(q))) return { kind: "plate", value: plate };
  return { kind: "text", value: q };
}

/** Words for ILIKE: 2+ characters, LIKE wildcards stripped, at most 6. */
export function searchWords(q: string): string[] {
  return Array.from(new Set(q.toLowerCase().replace(/[%_\\,()."'*]/g, " ").split(/\s+/).filter((w) => w.length >= 2))).slice(0, 6);
}

export function parseSearch(sp: Record<string, string | string[] | undefined>): ParsedSearch {
  const raw = (Array.isArray(sp.q) ? sp.q[0] : sp.q ?? "").slice(0, 120);
  const { kind, value } = classifyQuery(raw);
  const f = parseCaseFilters(sp);
  return {
    q: raw.trim(),
    kind,
    value,
    words: kind === "text" ? searchWords(value) : [],
    facets: { station: f.station, category: f.category, status: f.status, from: f.from, to: f.to },
  };
}

/** True when there is anything to search for (a query or at least one facet). */
export function hasCriteria(p: ParsedSearch): boolean {
  return p.kind !== "empty" || Object.values(p.facets).some(Boolean);
}

/** Human label for the footer: what the query was read as. */
export function kindLabel(k: QueryKind): string {
  return { empty: "filters only", crime_id: "case id", fir: "FIR number", plate: "vehicle plate", text: "words" }[k];
}
