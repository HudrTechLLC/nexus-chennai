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
