/**
 * Crime series as the console reads them (spec G2 /console/series, E4 Markovian; tables from 0002).
 * Pure types and helpers shared by the list, the detail page and the tests.
 * The pipeline creates series, members and dossiers (rule R3); the console only displays them.
 */

import { cellToLatLng, isValidCell } from "h3-js";
import { convexHull, padRing, type LonLat } from "@/lib/pulse";

// =====================
// Types
// =====================

export type SeriesStatus = "candidate" | "confirmed" | "closed";

/** One entry of series_overview() (0004_06_01). */
export type SeriesSummary = {
  series_id: string;
  name: string;
  status: SeriesStatus;
  created_at: string;
  updated_at: string;
  synthetic: boolean;
  has_dossier: boolean;
  dossier_at: string | null;
  members: number;
  stations: string[];
  categories: string[];
  week_from: string | null;
  week_to: string | null;
  cells: string[]; // H3 r8 cell per member (city-wide summary)
};

/**
 * The Markovian dossier the Series analyst persists into series.dossier (shape agreed with
 * nexus-chief / nexus-3, PR #65): the facade output plus model, receipts and run.
 * `model: null` means every chunk fell back to the extractive generator: no model wrote it.
 */
export type Dossier = {
  text: string;
  cited_ids: string[];
  chunks: number;
  record_count: number | null;
  tokens_projected: number | null;
  tokens_actual: number | null;
  model: string | null;
  receipt_id: string | null; // last chunk
  receipt_ids: string[];
  run_id: string | null;
  generated_at: string | null;
};

export type SeriesRow = {
  series_id: string;
  name: string;
  status: SeriesStatus;
  dossier: unknown;
  run_id: string | null;
  created_at: string;
  updated_at: string;
  synthetic: boolean;
};

/** What the timeline needs from a member crime (a CrimeBrief fits). */
export type MemberPoint = {
  crime_id: string;
  station_id: string;
  station_name: string;
  category: string;
  sub_type: string | null;
  fir_no: string | null;
  occurred_from: string | null;
  week: string | null;
  cell: string | null;
  lat: number | null;
  lon: number | null;
  full: boolean;
};

export const STATUS_LABEL: Record<SeriesStatus, string> = { candidate: "Candidate", confirmed: "Confirmed", closed: "Closed" };

export function isSeriesStatus(v: unknown): v is SeriesStatus {
  return v === "candidate" || v === "confirmed" || v === "closed";
}

// =====================
// Dossier
// =====================

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);

/** Reads series.dossier defensively. Returns null unless there is dossier text to show. */
export function parseDossier(raw: unknown): Dossier | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const d = raw as Record<string, unknown>;
  const text = str(d.text);
  if (!text) return null;
  return {
    text,
    cited_ids: Array.isArray(d.cited_ids) ? d.cited_ids.filter((x): x is string => typeof x === "string") : [],
    chunks: num(d.chunks) ?? (Array.isArray(d.chunks) ? d.chunks.length : 0),
    record_count: num(d.record_count),
    tokens_projected: num(d.tokens_projected),
    tokens_actual: num(d.tokens_actual),
    model: str(d.model),
    receipt_id: str(d.receipt_id),
    receipt_ids: Array.isArray(d.receipt_ids) ? d.receipt_ids.filter((x): x is string => typeof x === "string") : [],
    run_id: str(d.run_id),
    generated_at: str(d.generated_at),
  };
}

/** Who wrote the dossier text: the routed model, or the extractive fallback when no model did. */
export function dossierAuthor(d: Pick<Dossier, "model">): { label: string; model: boolean } {
  return d.model ? { label: d.model, model: true } : { label: "Extractive summary, no model", model: false };
}

/** Token saving of the chunked read against reading everything at once, e.g. 0.62; null if unknown. */
export function tokenSaving(d: Dossier): number | null {
  if (d.tokens_projected == null || d.tokens_actual == null || d.tokens_projected <= 0) return null;
  return Math.max(-1, Math.min(1, 1 - d.tokens_actual / d.tokens_projected));
}

/**
 * How to describe the token saving honestly. A dossier read in one chunk cannot save tokens (the
 * chunk overhead can even cost a little more), so show "none" with the reason instead of a negative %.
 */
export function savingLabel(d: Pick<Dossier, "chunks" | "tokens_projected" | "tokens_actual">): { text: string; hint: string | null } {
  const s = tokenSaving(d as Dossier);
  if (s == null) return { text: "—", hint: null };
  if (s > 0) return { text: `${Math.round(s * 100)}% fewer tokens`, hint: null };
  return {
    text: "none",
    hint: d.chunks <= 1 ? "The series fitted in one chunk; chunking only saves tokens on long series." : "This run used about as many tokens as a single read.",
  };
}

/** Splits cited ids into member crimes and other records (statements, tips, evidence). */
export function splitCitations(cited: string[], memberIds: string[]): { crimes: string[]; other: string[] } {
  const members = new Set(memberIds);
  const crimes: string[] = [];
  const other: string[] = [];
  for (const id of Array.from(new Set(cited))) (members.has(id) ? crimes : other).push(id);
  return { crimes, other };
}

// =====================
// Timeline and map
// =====================

/** Monday (UTC) of an ISO week like "2026-W14", as epoch ms; null if not an ISO week. */
export function isoWeekStart(week: string): number | null {
  const w = /^(\d{4})-W(\d{2})$/.exec(week);
  if (!w) return null;
  const year = Number(w[1]);
  const jan4 = Date.UTC(year, 0, 4);
  const jan4Dow = (new Date(jan4).getUTCDay() + 6) % 7; // Monday = 0
  return jan4 - jan4Dow * 86_400_000 + (Number(w[2]) - 1) * 7 * 86_400_000;
}

/** Sort key (epoch ms): exact time when the officer can read the crime, otherwise the start of its ISO week. */
export function memberSortKey(m: Pick<MemberPoint, "occurred_from" | "week">): number {
  if (m.occurred_from) {
    const t = Date.parse(m.occurred_from);
    if (Number.isFinite(t)) return t;
  }
  if (m.week) {
    const t = isoWeekStart(m.week);
    if (t != null) return t;
  }
  return Number.MAX_SAFE_INTEGER;
}

/** Members in time order, with the gap in days from the previous member when both times are exact. */
export function timeline<T extends MemberPoint>(members: T[]): (T & { gapDays: number | null })[] {
  const sorted = members.slice().sort((a, b) => memberSortKey(a) - memberSortKey(b) || a.crime_id.localeCompare(b.crime_id));
  return sorted.map((m, i) => {
    const prev = sorted[i - 1];
    const gap = prev?.occurred_from && m.occurred_from
      ? (Date.parse(m.occurred_from) - Date.parse(prev.occurred_from)) / 86_400_000
      : null;
    return { ...m, gapDays: gap == null ? null : Math.round(gap * 10) / 10 };
  });
}

/** A member's map position: the exact point where readable, else the centre of its H3 cell. */
export function memberLonLat(m: Pick<MemberPoint, "lat" | "lon" | "cell">): { p: LonLat; exact: boolean } | null {
  if (m.lat != null && m.lon != null) return { p: [m.lon, m.lat], exact: true };
  if (m.cell && isValidCell(m.cell)) {
    try {
      const [lat, lng] = cellToLatLng(m.cell);
      return { p: [lng, lat], exact: false };
    } catch {
      return null;
    }
  }
  return null;
}

/** Padded convex hull around the members (needs 3+ distinct points). */
export function seriesHull(points: LonLat[], pad = 0.004): LonLat[] | null {
  const uniq = Array.from(new Map(points.map((p) => [`${p[0].toFixed(6)},${p[1].toFixed(6)}`, p])).values());
  if (uniq.length < 3) return null;
  return padRing(convexHull(uniq), pad);
}

/** Bounding box [minLon, minLat, maxLon, maxLat] of points, or null. */
export function bbox(points: LonLat[]): [number, number, number, number] | null {
  if (points.length === 0) return null;
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const [x, y] of points) {
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  }
  return [x0, y0, x1, y1];
}

/**
 * Constellation thumbnail: member cells as points in a w×h box, with a path joining them in
 * list order. Pure (h3 → lon/lat → box), so the server renders it as plain SVG.
 */
export function constellation(cells: string[], w = 120, h = 72, margin = 8): { dots: { x: number; y: number; n: number }[] } {
  const counts = new Map<string, number>();
  for (const c of cells) counts.set(c, (counts.get(c) ?? 0) + 1);
  const pts: { p: LonLat; n: number }[] = [];
  counts.forEach((n, c) => {
    const ll = memberLonLat({ lat: null, lon: null, cell: c });
    if (ll) pts.push({ p: ll.p, n });
  });
  const box = bbox(pts.map((x) => x.p));
  if (!box) return { dots: [] };
  const [x0, y0, x1, y1] = box;
  const sx = x1 - x0 || 1e-6;
  const sy = y1 - y0 || 1e-6;
  const s = Math.min((w - 2 * margin) / sx, (h - 2 * margin) / sy);
  const ox = (w - sx * s) / 2;
  const oy = (h - sy * s) / 2;
  return {
    dots: pts.map(({ p, n }) => ({
      x: Math.round((ox + (p[0] - x0) * s) * 10) / 10,
      y: Math.round((h - (oy + (p[1] - y0) * s)) * 10) / 10, // north up
      n,
    })),
  };
}

/** "2026-W14 → 2026-W19", or one week, or an em dash. */
export function weekSpan(from: string | null, to: string | null): string {
  if (!from && !to) return "—";
  if (!to || from === to) return from ?? to ?? "—";
  return `${from} → ${to}`;
}

/** Splits ids into chunks so `.in()` filters stay well under URL limits. */
export function chunk<T>(items: T[], size = 100): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
