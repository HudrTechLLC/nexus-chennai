/**
 * Console-only area and map-link helpers (WS3-24): the officer counterpart of lib/publicArea.ts.
 *
 * publicArea.ts is deliberately r8-only and never carries a crime id. These helpers are for the signed-in
 * console only: /console/map accepts any tip cell resolution (r8 to r10) and a crime id, because the
 * console map reads crimes under row-level security (map_crimes runs as the officer).
 */
import { getResolution, isValidCell } from "h3-js";

// =====================
// Cells
// =====================

/** Tip cells the console map can frame: H3 resolutions 8 (~0.7 km²), 9 (~0.1 km²) and 10 (~0.015 km²). */
export const CONSOLE_CELL_RES = [8, 9, 10] as const;

/** Approximate H3 cell area by resolution, in km² (H3's average hexagon areas, rounded for display). */
export const CELL_AREA_KM2: Record<number, string> = { 8: "0.7", 9: "0.1", 10: "0.015" };

/** A valid H3 cell at a console resolution, lower-cased; null for anything else. */
export function consoleCell(raw: string | null | undefined): string | null {
  if (!raw || !/^[0-9a-f]{15}$/i.test(raw)) return null;
  const c = raw.toLowerCase();
  if (!isValidCell(c)) return null;
  return (CONSOLE_CELL_RES as readonly number[]).includes(getResolution(c)) ? c : null;
}

/** "Approximate area (~0.7 km²)" for a console cell; null when the cell is not one. */
export function cellAreaLabel(cell: string | null | undefined): string | null {
  const c = consoleCell(cell);
  return c ? `Approximate area (~${CELL_AREA_KM2[getResolution(c)]} km²)` : null;
}

// =====================
// Links into the console map
// =====================

/** A crime id as the console uses it (CHN-AD-2026-001182, CCTNS-…); nothing else goes into ?crime=. */
const CRIME_ID = /^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$/;

export function consoleCrimeId(raw: string | null | undefined): string | null {
  return raw && raw.length <= 64 && CRIME_ID.test(raw) ? raw : null;
}

/** /console/map framed on a tip's area cell. */
export function consoleCellMapHref(cell: string | null | undefined): string | null {
  const c = consoleCell(cell);
  return c ? `/console/map?cell=${c}` : null;
}

/** /console/map flown to a crime with its drawer open. Console only: never use it in a public page. */
export function consoleCrimeMapHref(crimeId: string | null | undefined): string | null {
  const id = consoleCrimeId(crimeId);
  return id ? `/console/map?crime=${encodeURIComponent(id)}` : null;
}

// =====================
// Tips: the crimes a tip is tied to
// =====================

export type TipCrimeSource = "appeal" | "tip" | "review";

/**
 * The crimes a tip is tied to, de-duplicated, in a stable order: the appeal's case first, then the crime
 * the public chose on a crime card (tips.about_crime_id, 0007_11), then crimes officers linked in reviews.
 */
export function tipLinkedCrimes(input: {
  appealCrimeId?: string | null;
  aboutCrimeId?: string | null;
  reviews?: { crime_id: string | null }[] | null;
}): { crimeId: string; source: TipCrimeSource }[] {
  const out: { crimeId: string; source: TipCrimeSource }[] = [];
  const add = (id: string | null | undefined, source: TipCrimeSource) => {
    const c = consoleCrimeId(id);
    if (c && !out.some((x) => x.crimeId === c)) out.push({ crimeId: c, source });
  };
  add(input.appealCrimeId, "appeal");
  add(input.aboutCrimeId, "tip");
  for (const r of input.reviews ?? []) add(r.crime_id, "review");
  return out;
}
