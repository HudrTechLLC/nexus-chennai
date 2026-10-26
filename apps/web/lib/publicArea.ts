import { cellToBoundary, getResolution, isValidCell } from "h3-js";
import { CITY } from "@/lib/city";

/**
 * Public "where it happened" helpers (appeal detail + /map?cell=). The public only ever sees an
 * H3 resolution-8 hexagon (about 0.7 km²), never a point, so anything else is refused.
 */

/** A public-resolution H3 cell id, or null for anything else (junk, other resolutions, injection). */
export function publicCell(raw: string | null | undefined): string | null {
  if (!raw || !/^[0-9a-f]{15}$/i.test(raw)) return null;
  const c = raw.toLowerCase();
  return isValidCell(c) && getResolution(c) === CITY.h3.public ? c : null;
}

/** [west, south, east, north] of a cell's hexagon. */
export function cellBounds(cell: string): [number, number, number, number] {
  const ring = cellToBoundary(cell, true);
  const lons = ring.map((p) => p[0]), lats = ring.map((p) => p[1]);
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
}

/** The public crime map focused on one area; null when the cell is not a public one. */
export function crimeMapHref(cell: string | null | undefined): string | null {
  const c = publicCell(cell);
  return c ? `/map?cell=${c}` : null;
}

/** "Add a tip about this appeal": the shared /tip/new prefill (resolved server-side from the appeal id). */
export function appealTipHref(appealId: string, kind?: "cctv"): string {
  return `/tip/new?appeal=${encodeURIComponent(appealId)}${kind ? `&kind=${kind}` : ""}`;
}

// =====================
// "Areas with crimes": keyboard access to the public crime cards
// =====================

/** A map cell as the public map receives it (0004_03 public_map_cells; 'area' from 0007_13). */
type AreaCell = { cell: string; by_category: Record<string, number>; appeal?: boolean; area?: string | null };

export type AreaRow = { cell: string; area: string; cards: number; appeal: boolean };

export const UNNAMED_AREA = "Unnamed area";

/**
 * One row per hexagon that has crime cards, under the current type filter. by_category already applies
 * the >=3 cutoff (only types with at least min_count crimes are listed), which is exactly when a crime
 * gets a public card, so the card count needs no new data. Most cards first, then by name.
 */
export function areaRows(cells: AreaCell[], type: string | null): AreaRow[] {
  return cells
    .map((c) => ({
      cell: c.cell,
      area: c.area?.trim() || UNNAMED_AREA,
      cards: type ? c.by_category[type] ?? 0 : Object.values(c.by_category).reduce((a, b) => a + b, 0),
      appeal: !!c.appeal,
    }))
    .filter((r) => r.cards > 0)
    .sort((a, b) => b.cards - a.cards || a.area.localeCompare(b.area) || a.cell.localeCompare(b.cell));
}

/** Esc closes the card panel, unless something inside already handled it or the user is typing. */
export function escapeClosesPanel(e: { key: string; defaultPrevented: boolean; target: { tagName?: string } | null }, panelOpen: boolean): boolean {
  if (!panelOpen || e.key !== "Escape" || e.defaultPrevented) return false;
  const tag = e.target?.tagName?.toUpperCase();
  return tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT";
}

/**
 * Where keyboard focus goes once a navigation settles: into the panel after a list row opened it, back to
 * the row after Esc closed it, otherwise nowhere (mouse users keep their focus).
 */
export function focusAfterNavigation(s: { pending: boolean; hex: string | null; openedFrom: string | null; returnTo: string | null }):
  { kind: "panel" } | { kind: "row"; cell: string } | null {
  if (s.pending) return null;
  if (s.hex && s.openedFrom === s.hex) return { kind: "panel" };
  if (!s.hex && s.returnTo) return { kind: "row", cell: s.returnTo };
  return null;
}
