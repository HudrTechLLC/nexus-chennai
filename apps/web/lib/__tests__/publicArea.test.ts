/**
 * Unit tests for the public area helpers (appeal "where it happened", /map?cell=).
 */
import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import { CITY } from "@/lib/city";
import { appealTipHref, cellBounds, crimeMapHref, publicCell } from "../publicArea";

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
