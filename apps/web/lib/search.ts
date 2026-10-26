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
  facets: Pick<CaseFilters, "station" | "category" | "status" | "from" | "to"> & ExtraFacets;
  /** "Similar MO" mode: rank look-alikes of this case instead of matching the box (SRCH-04). */
  similar: string | null;
};

/** SRCH-03 facets beyond the case-list ones. Time of day uses the Extractor's MO time band. */
export type ExtraFacets = {
  weapon: string | null;
  zone: string | null;
  mo: string | null; // one MO or visual tag, e.g. "two_wheeler_from_behind"
  tod: TimeBand | null;
  linked: "linked" | "unlinked" | null;
};
export const TIME_BANDS = ["early_morning", "morning", "afternoon", "evening", "night"] as const;
export type TimeBand = (typeof TIME_BANDS)[number];

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

/**
 * Spellings to match against persons.aliases (SRCH-05). Aliases are a text[], which PostgREST can only match
 * by whole element, so this offers the typed phrase and each word in lower, Title and UPPER case
 * ("pulsar raju" → "Pulsar Raju", "PULSAR RAJU", "pulsar", "Pulsar", …). Only letters, digits, space and
 * hyphen survive, so nothing can break out of the array literal.
 */
export function aliasVariants(words: string[]): string[] {
  const clean = words.map((w) => w.toLowerCase().replace(/[^a-z0-9 -]/g, "")).filter((w) => w.length >= 2);
  if (clean.length === 0) return [];
  const title = (t: string) => t.replace(/(^|[ -])([a-z])/g, (_m, p: string, c: string) => p + c.toUpperCase());
  const out = new Set<string>();
  for (const t of [clean.join(" "), ...clean]) for (const v of [t, title(t), t.toUpperCase()]) out.add(v);
  return Array.from(out).slice(0, 24);
}

/** PostgREST or-filter for person search: a name fragment, or an exact alias in any common spelling. */
export function personFilter(words: string[]): string {
  const byName = words.map((w) => `name.ilike.%${w}%`);
  const aliases = aliasVariants(words);
  return [...byName, ...(aliases.length ? [`aliases.ov.{${aliases.map((v) => `"${v}"`).join(",")}}`] : [])].join(",");
}

export function parseSearch(sp: Record<string, string | string[] | undefined>): ParsedSearch {
  const raw = (Array.isArray(sp.q) ? sp.q[0] : sp.q ?? "").slice(0, 120);
  const { kind, value } = classifyQuery(raw);
  const f = parseCaseFilters(sp);
  const one = (k: string) => { const v = sp[k]; return (Array.isArray(v) ? v[0] : v)?.trim() || null; };
  const word = (v: string | null, max = 40) => (v && /^[a-z0-9_ -]{2,40}$/i.test(v) ? v.slice(0, max).toLowerCase().replace(/[ -]+/g, "_") : null);
  const tod = one("tod");
  const linked = one("linked");
  const similar = one("similar")?.toUpperCase() ?? null;
  return {
    q: raw.trim(),
    kind,
    value,
    words: kind === "text" ? searchWords(value) : [],
    facets: {
      station: f.station, category: f.category, status: f.status, from: f.from, to: f.to,
      weapon: word(one("weapon")),
      zone: one("zone") && /^[A-Za-z .-]{2,40}$/.test(one("zone") as string) ? (one("zone") as string) : null,
      mo: word(one("mo")),
      tod: tod && (TIME_BANDS as readonly string[]).includes(tod) ? (tod as TimeBand) : null,
      linked: linked === "linked" || linked === "unlinked" ? linked : null,
    },
    similar: similar && CRIME_ID_RE.test(similar) ? similar : null,
  };
}

/** True when there is anything to search for (a query or at least one facet). */
export function hasCriteria(p: ParsedSearch): boolean {
  return p.kind !== "empty" || !!p.similar || Object.values(p.facets).some(Boolean);
}

/** Human label for the footer: what the query was read as. */
export function kindLabel(k: QueryKind): string {
  return { empty: "filters only", crime_id: "case id", fir: "FIR number", plate: "vehicle plate", text: "words" }[k];
}
