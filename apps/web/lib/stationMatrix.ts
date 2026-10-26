/**
 * Station × station link matrix (spec G2 /console/stations).
 * The station_link_matrix() RPC (0004_06_01) counts link alerts per unordered station pair and
 * status; these pure helpers turn that into a grid the page and the tests share.
 */

import type { AlertStatus } from "@/lib/alerts";

// =====================
// Types (RPC payload)
// =====================

export type MatrixCell = {
  a: string; // station id, a <= b; a === b for an alert inside one station
  b: string;
  status: AlertStatus;
  kind: "pair" | "series" | "hotspot";
  n: number;
  alert_ids: string[]; // newest first, capped by the RPC
};

export type MatrixStation = { id: string; name: string; zone: string | null };

export type StationCount = { station: string; status: AlertStatus; n: number };

export type MatrixPayload = { cells: MatrixCell[]; per_station: StationCount[]; stations: MatrixStation[]; alerts: number };

export type PairCounts = { approved: number; pending: number; rejected: number; total: number; alertIds: string[] };

export type StationMatrix = {
  stations: MatrixStation[]; // only stations that appear in at least one alert, by zone then name
  pairs: Record<string, PairCounts>; // key from pairKey()
  perStation: Record<string, PairCounts>; // every alert touching the station, once
  maxCross: number; // largest off-diagonal total, for the colour scale
  crossTotal: number; // alerts counted on cross-station pairs (a pair alert spanning 3 stations counts in 3 cells)
  topPairs: { a: string; b: string; counts: PairCounts }[]; // cross-station pairs, most links first
};

// =====================
// Helpers
// =====================

/** Order-independent key for a station pair. */
export function pairKey(a: string, b: string): string {
  return a <= b ? `${a}|${b}` : `${b}|${a}`;
}

function empty(): PairCounts {
  return { approved: 0, pending: 0, rejected: 0, total: 0, alertIds: [] };
}

function add(target: PairCounts, cell: MatrixCell) {
  target[cell.status] += cell.n;
  target.total += cell.n;
  for (const id of cell.alert_ids ?? []) if (!target.alertIds.includes(id)) target.alertIds.push(id);
}

/** Builds the grid. `statuses` filters which alert statuses count (default: all three). */
export function buildMatrix(payload: MatrixPayload, statuses: AlertStatus[] = ["approved", "pending", "rejected"]): StationMatrix {
  const pairs: Record<string, PairCounts> = {};
  const perStation: Record<string, PairCounts> = {};
  const seen = new Set<string>();

  for (const c of payload.cells) {
    if (!statuses.includes(c.status) || c.n <= 0) continue;
    add((pairs[pairKey(c.a, c.b)] ??= empty()), c);
    seen.add(c.a);
    seen.add(c.b);
  }
  // Distinct alerts per station come from the RPC: a series alert spanning 3 stations sits in
  // several cells but counts once for each station.
  for (const p of payload.per_station ?? []) {
    if (!statuses.includes(p.status) || p.n <= 0) continue;
    const ps = (perStation[p.station] ??= empty());
    ps[p.status] += p.n;
    ps.total += p.n;
  }

  const known = new Map(payload.stations.map((s) => [s.id, s]));
  const stations = Array.from(seen)
    .map((id) => known.get(id) ?? { id, name: id, zone: null })
    .sort((x, y) => (x.zone ?? "~").localeCompare(y.zone ?? "~") || x.name.localeCompare(y.name));

  let maxCross = 0;
  let crossTotal = 0;
  const topPairs: StationMatrix["topPairs"] = [];
  for (const [k, counts] of Object.entries(pairs)) {
    const [a, b] = k.split("|");
    if (a === b) continue;
    maxCross = Math.max(maxCross, counts.total);
    crossTotal += counts.total;
    topPairs.push({ a, b, counts });
  }
  topPairs.sort((x, y) => y.counts.total - x.counts.total || x.a.localeCompare(y.a) || x.b.localeCompare(y.b));

  return { stations, pairs, perStation, maxCross, crossTotal, topPairs };
}

/** Counts for a pair, or zeros. */
export function cellCounts(m: StationMatrix, a: string, b: string): PairCounts {
  return m.pairs[pairKey(a, b)] ?? empty();
}

/** 0..1 intensity for a cell's shade (square-root scale so small counts stay visible). */
export function intensity(total: number, max: number): number {
  if (total <= 0 || max <= 0) return 0;
  return Math.min(1, Math.sqrt(total / max));
}

/** Short station label: drops a "PS-" prefix and the police-district code ("Adyar (J2)" → "Adyar"). */
export function shortStation(name: string): string {
  return name.replace(/^PS-/, "").replace(/\s*\([A-Z]\d+\)$/, "").replace(/-[A-Z]\d+$/, "").replace(/_/g, " ").trim();
}

/** Parses the status filter from the URL (?status=approved,pending). Unknown values are dropped. */
export function parseStatuses(raw: string | undefined): AlertStatus[] {
  const all: AlertStatus[] = ["approved", "pending", "rejected"];
  if (!raw) return all;
  const picked = raw.split(",").filter((s): s is AlertStatus => (all as string[]).includes(s));
  return picked.length ? picked : all;
}
