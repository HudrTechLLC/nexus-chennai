/**
 * Unit tests for the console area helpers (WS3-24: tip -> console map).
 */
import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import {
  cellAreaLabel, consoleCell, consoleCellMapHref, consoleCrimeId, consoleCrimeMapHref, tipLinkedCrimes,
} from "../consoleArea";
import { crimeMapHref } from "../publicArea";

const at = (res: number) => latLngToCell(13.0067, 80.2573, res);

describe("consoleCell", () => {
  it("accepts r8, r9 and r10 tip cells, case-insensitively", () => {
    for (const r of [8, 9, 10]) expect(consoleCell(at(r).toUpperCase())).toBe(at(r));
  });
  it("refuses other resolutions and junk", () => {
    expect(consoleCell(at(7))).toBeNull();
    expect(consoleCell(at(11))).toBeNull();
    expect(consoleCell(undefined)).toBeNull();
    expect(consoleCell("8a618c4e65fffff' or 1=1")).toBeNull();
    expect(consoleCell("zzzzzzzzzzzzzzz")).toBeNull();
  });
});

describe("cellAreaLabel", () => {
  it("labels the area from the resolution", () => {
    expect(cellAreaLabel(at(8))).toBe("Approximate area (~0.7 km²)");
    expect(cellAreaLabel(at(9))).toBe("Approximate area (~0.1 km²)");
    expect(cellAreaLabel(at(10))).toBe("Approximate area (~0.015 km²)");
    expect(cellAreaLabel("nope")).toBeNull();
  });
});

describe("console map links", () => {
  it("builds /console/map links for a cell and a crime", () => {
    expect(consoleCellMapHref(at(9))).toBe(`/console/map?cell=${at(9)}`);
    expect(consoleCrimeMapHref("CHN-AD-2026-001182")).toBe("/console/map?crime=CHN-AD-2026-001182");
    expect(consoleCrimeMapHref("CCTNS-J2-1182-2024")).toBe("/console/map?crime=CCTNS-J2-1182-2024");
  });
  it("refuses anything that is not a crime id", () => {
    expect(consoleCrimeId("x\" onclick=")).toBeNull();
    expect(consoleCrimeId("../../etc")).toBeNull();
    expect(consoleCrimeMapHref("")).toBeNull();
  });
  it("the public map link can never carry a crime id", () => {
    expect(crimeMapHref("CHN-AD-2026-001182")).toBeNull();
  });
});

describe("tipLinkedCrimes", () => {
  it("orders appeal, then the tip's own crime, then reviews, without duplicates or blanks", () => {
    expect(tipLinkedCrimes({
      appealCrimeId: "CHN-AD-2026-001182", aboutCrimeId: "CHN-VL-2026-000877",
      reviews: [{ crime_id: "CHN-AD-2026-001182" }, { crime_id: null }, { crime_id: "CHN-KU-2025-000078" }],
    })).toEqual([
      { crimeId: "CHN-AD-2026-001182", source: "appeal" },
      { crimeId: "CHN-VL-2026-000877", source: "tip" },
      { crimeId: "CHN-KU-2025-000078", source: "review" },
    ]);
  });
  it("is empty when nothing is linked", () => {
    expect(tipLinkedCrimes({})).toEqual([]);
    expect(tipLinkedCrimes({ appealCrimeId: null, aboutCrimeId: "", reviews: null })).toEqual([]);
  });
});
