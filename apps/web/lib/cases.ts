/**
 * Case list and case file: pure helpers shared by the pages and the tests (spec G2, B4, J5).
 * No Supabase calls here; data access lives in lib/casesData.ts.
 */

// =====================
// Types
// =====================

export const CASE_STATUSES = ["registered", "under_investigation", "charge_sheeted", "undetected", "closed", "transferred"] as const;
export type CaseStatus = (typeof CASE_STATUSES)[number];

export type CaseFilters = {
  station: string | null;
  category: string | null;
  status: CaseStatus | null;
  from: string | null; // YYYY-MM-DD, city time
  to: string | null; // YYYY-MM-DD, city time, inclusive
  fir: string | null; // FIR number, e.g. "1182/2026" or "1182"
  plate: string | null; // plate fragment, "?" = unread character
  page: number; // 1-based
};

export const PAGE_SIZE = 50;

/**
 * Crime categories and sub-types as stored in crimes.category / sub_type (the generator's
 * taxonomy, spec D3.1). Used by the case filters and the FIR form's category → sub-type picker.
 */
export const CRIME_TYPES: Record<string, string[]> = {
  robbery: ["chain_snatching", "mobile_snatching", "street_robbery", "cab_robbery"],
  house_break: ["night_house_break", "day_house_break"],
  theft: ["two_wheeler_theft", "car_theft", "shop_theft", "pickpocket"],
  hurt: ["assault", "attempt_murder"],
  homicide: ["murder"],
  crimes_against_women: ["stalking"],
  kidnapping: ["kidnapping"],
  cheating: ["cheating"],
};
export const CATEGORIES = Object.keys(CRIME_TYPES);

export type TimelineKind = "occurred" | "fir" | "statement" | "evidence" | "diary" | "alert" | "review" | "tip";
export type TimelineItem = { at: string; kind: TimelineKind; label: string; href?: string };

// =====================
// Filters (URL search params)
// =====================

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function clean(v: string | string[] | undefined, max = 64): string | null {
  const s = (Array.isArray(v) ? v[0] : v)?.trim();
  return s ? s.slice(0, max) : null;
}

/** Parses the case-list query string. Anything malformed is dropped, never passed to a query. */
export function parseCaseFilters(sp: Record<string, string | string[] | undefined>): CaseFilters {
  const station = clean(sp.station);
  const category = clean(sp.category);
  const knownCategory = category && CATEGORIES.includes(category) ? category : null;
  const status = clean(sp.status);
  const from = clean(sp.from, 10);
  const to = clean(sp.to, 10);
  const page = Number.parseInt(clean(sp.page, 6) ?? "1", 10);
  return {
    station: station && ID_RE.test(station) ? station : null,
    category: knownCategory,
    status: status && (CASE_STATUSES as readonly string[]).includes(status) ? (status as CaseStatus) : null,
    from: from && DATE_RE.test(from) ? from : null,
    to: to && DATE_RE.test(to) ? to : null,
    fir: normaliseFir(clean(sp.fir, 20)),
    plate: normalisePlate(clean(sp.plate, 16)),
    page: Number.isFinite(page) && page > 0 ? Math.min(page, 1000) : 1,
  };
}

/** Builds a case-list URL from filters, keeping only the set ones. */
export function casesHref(f: Partial<CaseFilters>, base = "/console/cases"): string {
  const qs = new URLSearchParams();
  (["station", "category", "status", "from", "to", "fir", "plate"] as const).forEach((k) => {
    const v = f[k];
    if (v) qs.set(k, String(v));
  });
  if (f.page && f.page > 1) qs.set("page", String(f.page));
  const s = qs.toString();
  return s ? `${base}?${s}` : base;
}

/** "1182/2026" stays; "1182" stays (matches any year); anything else is rejected. */
export function normaliseFir(v: string | null): string | null {
  if (!v) return null;
  const s = v.replace(/\s+/g, "");
  return /^\d{1,6}(\/\d{4})?$/.test(s) ? s : null;
}

/** Plates are stored upper-case with spaces removed and "?" for unread characters ("TN09??4471"). */
export function normalisePlate(v: string | null): string | null {
  if (!v) return null;
  const s = v.toUpperCase().replace(/[\s.-]+/g, "").replace(/[*…]/g, "?");
  return /^[A-Z0-9?]{3,12}$/.test(s) ? s : null; // 3+ so a fragment narrows the list
}

/**
 * ILIKE pattern for a plate fragment. A typed "?" matches any one character ("_"); every other
 * character must match itself or a stored "?" (an unread character on the record). Wildcards
 * in the user's text are impossible after normalisePlate, so nothing needs escaping.
 */
export function plateIlike(fragment: string): string {
  return `%${fragment.split("").map((ch) => (ch === "?" ? "_" : ch)).join("")}%`;
}

/** True when a stored plate pattern can be the typed fragment (used to rank and to double-check ILIKE hits). */
export function plateMatches(stored: string | null, fragment: string): boolean {
  if (!stored) return false;
  const s = stored.toUpperCase();
  for (let i = 0; i + fragment.length <= s.length; i++) {
    let ok = true;
    for (let j = 0; j < fragment.length && ok; j++) {
      const a = s[i + j];
      const b = fragment[j];
      ok = a === "?" || b === "?" || a === b;
    }
    if (ok) return true;
  }
  return false;
}

/** Start/end of a city-time day range as ISO instants, for occurred_from filters. */
export function dayRange(from: string | null, to: string | null, offset = "+05:30"): { gte: string | null; lt: string | null } {
  const gte = from ? new Date(`${from}T00:00:00${offset}`).toISOString() : null;
  let lt: string | null = null;
  if (to) {
    const d = new Date(`${to}T00:00:00${offset}`);
    d.setUTCDate(d.getUTCDate() + 1);
    lt = d.toISOString();
  }
  return { gte, lt };
}

/** Mirrors public.can_write_crime (0002): admin and supervisor anywhere, a station officer on their own station. */
export function canWriteCase(role: string | null | undefined, ownStation: string | null | undefined, caseStation: string): boolean {
  if (role === "admin" || role === "supervisor") return true;
  return role === "station_officer" && !!ownStation && ownStation === caseStation;
}

// =====================
// Display
// =====================

/**
 * Masks personal identifiers in free text before display (spec J5): phone numbers and
 * Aadhaar-like 12-digit numbers. Names are already masked at the source (witness_ref etc.).
 */
export function maskPii(text: string): string {
  return text
    .replace(/\b\d{4}[ -]?\d{4}[ -]?\d{4}\b/g, "XXXX XXXX XXXX")
    .replace(/(?:\+91[ -]?)?\b[6-9]\d{4}[ -]?\d{5}\b/g, "XXXXX XXXXX");
}

/** "crimes_against_women" -> "crimes against women". */
export function humanise(v: string | null | undefined): string {
  return v ? v.replace(/_/g, " ") : "—";
}

/** One line for a structured descriptor object ({build: "thin", age_band: "20-30", ...}). */
export function describe(obj: Record<string, unknown> | null | undefined): string {
  if (!obj) return "—";
  const parts = Object.keys(obj)
    .filter((k) => obj[k] !== null && obj[k] !== undefined && obj[k] !== "" && !(Array.isArray(obj[k]) && (obj[k] as unknown[]).length === 0))
    .map((k) => `${humanise(k)}: ${Array.isArray(obj[k]) ? (obj[k] as unknown[]).join(", ") : String(obj[k])}`);
  return parts.length ? parts.join(" · ") : "—";
}

/** Flattens an Extractor MO object to [label, value] rows, skipping empty values. */
export function moRows(mo: Record<string, unknown> | null | undefined): [string, string][] {
  if (!mo) return [];
  return Object.keys(mo)
    .sort()
    .map((k): [string, unknown] => [k, mo[k]])
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]): [string, string] => [k, Array.isArray(v) ? v.map((x) => humanise(String(x))).join(", ") : humanise(String(v))]);
}

// =====================
// Officer review of extracted MO (0007_01 review_features)
// =====================

/** The D3.2 "mo" fields an officer may correct (same list as review_features in SQL). */
export const MO_FIELDS = ["approach", "offender_count", "target", "target_item", "escape", "violence", "time_band", "place_type", "disguise", "verbal"] as const;
export type MoField = (typeof MO_FIELDS)[number];
const LIST_FIELDS: MoField[] = ["place_type", "disguise"];

/** An MO value as the review form shows it: lists comma-separated, labels with spaces. */
export function moToText(v: unknown): string {
  if (v === null || v === undefined) return "";
  return Array.isArray(v) ? v.map((x) => String(x).replace(/_/g, " ")).join(", ") : String(v).replace(/_/g, " ");
}

function textToMo(field: MoField, text: string): unknown {
  const snake = (s: string) => s.trim().toLowerCase().replace(/\s+/g, "_");
  const t = text.trim();
  if (field === "offender_count") return t === "" ? null : Number.parseInt(t, 10);
  if (LIST_FIELDS.includes(field)) return t === "" ? [] : t.split(",").map(snake).filter(Boolean);
  return t === "" ? null : snake(t);
}

/**
 * Only the fields the officer changed, in the stored shape (snake_case values, lists as arrays).
 * Returns an error for an invalid offender count.
 */
export function moCorrections(mo: Record<string, unknown>, edited: Partial<Record<MoField, string>>): { corrections: Record<string, unknown> } | { error: string } {
  const out: Record<string, unknown> = {};
  for (const f of MO_FIELDS) {
    const text = edited[f];
    if (text === undefined || moToText(mo[f]) === text.trim()) continue;
    const v = textToMo(f, text);
    if (f === "offender_count" && v !== null && (!Number.isInteger(v) || (v as number) < 0 || (v as number) > 50)) return { error: "Offender count must be a whole number." };
    if (JSON.stringify(v) !== JSON.stringify(mo[f] ?? (LIST_FIELDS.includes(f) ? [] : null))) out[f] = v;
  }
  return { corrections: out };
}

/** Merges dated events into one newest-first timeline; undated items are skipped. */
export function buildTimeline(items: (TimelineItem | null | undefined)[]): TimelineItem[] {
  return items
    .filter((i): i is TimelineItem => !!i && !!i.at && !Number.isNaN(Date.parse(i.at)))
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}
