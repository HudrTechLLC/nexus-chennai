import { cellToLatLng, cellToParent, getResolution, isValidCell, latLngToCell } from "h3-js";

/**
 * "Roughly where?" area sizes for the anonymous tip (WS4-15, spec J1). The tipster picks an H3 cell at
 * one of three sizes; the finest is resolution 10 (about 0.015 km²). We always keep an AREA, never a point:
 * the tapped or searched point stays in the browser and only the cell id is sent.
 */

// =====================
// Sizes
// =====================

export type AreaRes = 8 | 9 | 10;

export const AREA_SIZES: { res: AreaRes; label: string; km2: string }[] = [
  { res: 8, label: "Large", km2: "~0.7 km²" },
  { res: 9, label: "Medium", km2: "~0.1 km²" },
  { res: 10, label: "Small", km2: "~0.015 km²" },
];

export const DEFAULT_AREA_RES: AreaRes = 9;

/** The cell a tip may carry: H3 resolution 8, 9 or 10 (hex strings start 88, 89, 8a). */
export const TIP_CELL_RE = /^8[89a][0-9a-f]{13}$/;

export function isTipCell(cell: string | null | undefined): cell is string {
  return !!cell && TIP_CELL_RE.test(cell) && isValidCell(cell) && [8, 9, 10].includes(getResolution(cell));
}

export function cellRes(cell: string): AreaRes {
  return getResolution(cell) as AreaRes;
}

// =====================
// Moving between sizes
// =====================

export type Point = { lat: number; lng: number };

/**
 * The cell at `res` for the same spot. Coarser: the parent cell. Finer: the cell around the point the
 * tipster tapped or searched (kept in the browser only), or the centre of the current cell if there is none.
 */
export function resizeCell(cell: string | null, res: AreaRes, point: Point | null): string | null {
  if (!cell || !isTipCell(cell)) return point ? latLngToCell(point.lat, point.lng, res) : null;
  const from = cellRes(cell);
  if (res === from) return cell;
  if (res < from) return cellToParent(cell, res);
  const p = point && cellToParent(latLngToCell(point.lat, point.lng, res), from) === cell
    ? point
    : (([lat, lng]) => ({ lat, lng }))(cellToLatLng(cell));
  return latLngToCell(p.lat, p.lng, res);
}

/** Zoom levels from which the picker suggests the next finer size. */
export const SUGGEST_ZOOM: Record<9 | 10, number> = { 9: 14, 10: 16 };

/**
 * The finer size to SUGGEST at this zoom, or the current one. Only a hint: the size changes only when the
 * tipster taps Large/Medium/Small (J1; zooming is not consent to a more precise area). Never suggests bigger.
 */
export function suggestedRes(zoom: number, res: AreaRes): AreaRes {
  if (res < 10 && zoom >= SUGGEST_ZOOM[10]) return 10;
  if (res < 9 && zoom >= SUGGEST_ZOOM[9]) return 9;
  return res;
}

/** A zoom that shows a cell of this size comfortably. */
export function zoomFor(res: AreaRes): number {
  return res === 8 ? 13 : res === 9 ? 14.5 : 16;
}
