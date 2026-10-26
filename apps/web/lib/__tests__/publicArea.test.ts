/**
 * Unit tests for the public area helpers (appeal "where it happened", /map?cell=).
 */
import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import { CITY } from "@/lib/city";
import { appealTipHref, areaRows, cellBounds, crimeMapHref, escapeClosesPanel, focusAfterNavigation, publicCell, UNNAMED_AREA } from "../publicArea";

const ADYAR = latLngToCell(13.0067, 80.2573, CITY.h3.public);

describe("publicCell", () => {
  it("accepts a public-resolution cell, case-insensitively", () => {
    expect(publicCell(ADYAR)).toBe(ADYAR);
    expect(publicCell(ADYAR.toUpperCase())).toBe(ADYAR);
  });
  it("refuses junk, other resolutions and anything that is not a bare cell id", () => {
    expect(publicCell(undefined)).toBeNull();
    expect(publicCell("")).toBeNull();
    expect(publicCell("not-a-cell")).toBeNull();
    expect(publicCell(latLngToCell(13.0067, 80.2573, CITY.h3.public + 1))).toBeNull(); // finer = closer to a point
    expect(publicCell(`${ADYAR}&x=1`)).toBeNull();
  });
});

describe("cellBounds", () => {
  it("is a small box around the hexagon", () => {
    const [w, s, e, n] = cellBounds(ADYAR);
    expect(w).toBeLessThan(80.2573);
    expect(e).toBeGreaterThan(80.2573);
    expect(s).toBeLessThan(13.0067);
    expect(n).toBeGreaterThan(13.0067);
    expect(e - w).toBeLessThan(0.03);
  });
});

describe("crimeMapHref", () => {
  it("links the crime map to the area, or nothing for a bad cell", () => {
    expect(crimeMapHref(ADYAR)).toBe(`/map?cell=${ADYAR}`);
    expect(crimeMapHref("junk")).toBeNull();
  });
});

describe("appealTipHref", () => {
  it("opens the tip form prefilled from the appeal id (escaped), optionally as CCTV", () => {
    expect(appealTipHref("PI-2026-4F2463")).toBe("/tip/new?appeal=PI-2026-4F2463");
    expect(appealTipHref("PI-2026-4F2463", "cctv")).toBe("/tip/new?appeal=PI-2026-4F2463&kind=cctv");
    expect(appealTipHref("a&b")).toBe("/tip/new?appeal=a%26b");
  });
});

describe("areaRows", () => {
  const cells: { cell: string; by_category: Record<string, number>; appeal: boolean; area?: string | null }[] = [
    { cell: "a", by_category: { theft: 4, robbery: 3 }, appeal: false, area: "Adyar" },
    { cell: "b", by_category: {}, appeal: true, area: null }, // under the cutoff: no cards, no row
    { cell: "c", by_category: { theft: 9 }, appeal: true, area: "Velachery" },
    { cell: "d", by_category: { robbery: 7 }, appeal: false },
  ];
  it("lists only hexagons with cards, most cards first, with the card count from by_category", () => {
    expect(areaRows(cells, null)).toEqual([
      { cell: "c", area: "Velachery", cards: 9, appeal: true },
      { cell: "a", area: "Adyar", cards: 7, appeal: false },
      { cell: "d", area: UNNAMED_AREA, cards: 7, appeal: false },
    ]);
  });
  it("respects the crime-type filter", () => {
    expect(areaRows(cells, "robbery").map((r) => [r.cell, r.cards])).toEqual([["d", 7], ["a", 3]]);
    expect(areaRows(cells, "cheating")).toEqual([]);
  });
});

describe("keyboard open / close", () => {
  const ev = (key: string, tagName = "BUTTON", defaultPrevented = false) => ({ key, defaultPrevented, target: { tagName } });
  it("Esc closes an open panel, but not while typing or when already handled", () => {
    expect(escapeClosesPanel(ev("Escape"), true)).toBe(true);
    expect(escapeClosesPanel(ev("Escape"), false)).toBe(false);
    expect(escapeClosesPanel(ev("Enter"), true)).toBe(false);
    expect(escapeClosesPanel(ev("Escape", "INPUT"), true)).toBe(false);
    expect(escapeClosesPanel(ev("Escape", "BUTTON", true), true)).toBe(false);
  });
  it("moves focus into the panel after a list pick, and back to the row after Esc", () => {
    // Enter on row "c": navigation pending, then settled with ?hex=c
    expect(focusAfterNavigation({ pending: true, hex: null, openedFrom: "c", returnTo: null })).toBeNull();
    expect(focusAfterNavigation({ pending: false, hex: "c", openedFrom: "c", returnTo: null })).toEqual({ kind: "panel" });
    // Esc: navigation settles with no hex, focus returns to row "c"
    expect(focusAfterNavigation({ pending: false, hex: null, openedFrom: null, returnTo: "c" })).toEqual({ kind: "row", cell: "c" });
    // a mouse click on the map: focus is left alone
    expect(focusAfterNavigation({ pending: false, hex: "a", openedFrom: null, returnTo: null })).toBeNull();
  });
});
