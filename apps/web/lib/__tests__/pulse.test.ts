import { describe, expect, it } from "vitest";
import {
  arcPath, binDaily, binHours, catKey, cone, convexHull, decodeCrimes, DAY_MS, hhmm, inClockArc, km, localDay,
  boundsOf, byCount, initialFrame, overlayPadding, decodeFacets, facetIds, monthWindows, padRing, passes, UNKNOWN_ZONE, zoneStations, pulseTier, tzOffsetMinutes, type CatKey, type CrimeFilter, type MapCrime,
} from "../pulse";

describe("catKey", () => {
  it("maps categories and sub-types to the G3 palette", () => {
    expect(catKey("robbery", "chain_snatching")).toBe("robbery");
    expect(catKey("house_break", null)).toBe("burglary");
    expect(catKey("theft", "motorcycle_theft")).toBe("vehicle_theft");
    expect(catKey("cheating", "otp_fraud")).toBe("cyber_fraud");
    expect(catKey("murder")).toBe("homicide");
    expect(catKey("something_else")).toBe("other");
  });
});

describe("pulseTier", () => {
  const now = Date.UTC(2026, 9, 26);
  it("uses age at the playhead", () => {
    expect(pulseTier(now - 2 * 3600_000, now)).toBe("fast");
    expect(pulseTier(now - 3 * DAY_MS, now)).toBe("medium");
    expect(pulseTier(now - 30 * DAY_MS, now)).toBe("static");
    expect(pulseTier(now + 1000, now)).toBe("future");
  });
});

describe("inClockArc", () => {
  it("handles plain arcs", () => {
    expect(inClockArc(19 * 60, 19 * 60, 23 * 60)).toBe(true);
    expect(inClockArc(23 * 60, 19 * 60, 23 * 60)).toBe(false);
    expect(inClockArc(10 * 60, 19 * 60, 23 * 60)).toBe(false);
  });
  it("wraps past midnight (22:00 to 02:00)", () => {
    expect(inClockArc(23 * 60, 22 * 60, 2 * 60)).toBe(true);
    expect(inClockArc(60, 22 * 60, 2 * 60)).toBe(true);
    expect(inClockArc(2 * 60, 22 * 60, 2 * 60)).toBe(false);
    expect(inClockArc(12 * 60, 22 * 60, 2 * 60)).toBe(false);
  });
  it("treats equal ends as the whole day", () => expect(inClockArc(5, 0, 0)).toBe(true));
});

describe("histograms", () => {
  it("bins by local day using the city offset", () => {
    const off = 330; // IST
    const d0 = localDay(Date.UTC(2026, 9, 1, 0, 0), off);
    // 2026-10-01 20:00 UTC is 2026-10-02 01:30 IST: the next local day.
    const times = [Date.UTC(2026, 9, 1, 5), Date.UTC(2026, 9, 1, 20), Date.UTC(2026, 9, 3, 5)];
    expect(binDaily(times, d0, d0 + 2, off)).toEqual([1, 1, 1]);
  });
  it("bins minutes into 24 hours", () => {
    const b = binHours([0, 59, 60, 1439]);
    expect(b[0]).toBe(2);
    expect(b[1]).toBe(1);
    expect(b[23]).toBe(1);
  });
  it("reads timezone offsets", () => {
    expect(tzOffsetMinutes("Asia/Kolkata", Date.UTC(2026, 9, 26, 12))).toBe(330);
    expect(tzOffsetMinutes("UTC", Date.UTC(2026, 0, 1))).toBe(0);
  });
});

describe("geometry", () => {
  it("convex hull drops interior points and closes the ring", () => {
    const ring = convexHull([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]]);
    expect(ring).toHaveLength(5);
    expect(ring[0]).toEqual(ring[4]);
    expect(ring).not.toContainEqual([0.5, 0.5]);
  });
  it("hull of fewer than 3 distinct points is empty", () => {
    expect(convexHull([[0, 0], [0, 0], [1, 1]])).toEqual([]);
  });
  it("padRing grows the ring", () => {
    const r = padRing(convexHull([[0, 0], [2, 0], [1, 2]]), 0.5);
    expect(Math.min(...r.map((p) => p[0]))).toBeLessThan(0);
  });
  it("arcPath starts and ends on the crimes and bends off the chord", () => {
    const { path, t } = arcPath([80, 13], [80.1, 13], 10);
    expect(path[0]).toEqual([80, 13]);
    expect(path[10][0]).toBeCloseTo(80.1);
    expect(t[10]).toBe(1);
    expect(Math.abs(path[5][1] - 13)).toBeGreaterThan(0.001);
  });
  it("km is about right for Adyar to Velachery", () => {
    expect(km([80.2565, 13.0012], [80.2209, 12.979])).toBeGreaterThan(4);
    expect(km([80.2565, 13.0012], [80.2209, 12.979])).toBeLessThan(5);
  });
  it("cone opens around the heading", () => {
    const c = cone(80, 13, 0, 90, 100);
    expect(c[0]).toEqual([80, 13]);
    expect(Math.max(...c.map((p) => p[1]))).toBeGreaterThan(13); // north-facing
  });
});

describe("decode and filter", () => {
  const cols = {
    id: ["A", "B"], lon: [80.1, 80.2], lat: [13.0, 13.1], t: [Date.UTC(2026, 9, 1, 14), Date.UTC(2026, 9, 20, 2)],
    mod: [19 * 60 + 30, 7 * 60 + 30], cat: ["robbery", "house_break"], sub: ["chain_snatching", null], sev: [3, 2],
    st: ["PS-ADYAR-J2", "PS-VELACHERY-J7"], status: ["under_investigation", "registered"], linked: [true, false], series: ["S1", null],
  };
  const crimes = decodeCrimes(cols);
  const base: CrimeFilter = {
    cats: new Set<CatKey>(["robbery", "burglary"]), from: 0, to: Date.UTC(2027, 0, 1), clock: null,
    linkedOnly: false, seriesOnly: false, stations: new Set(), statuses: new Set(),
  };
  it("decodes columnar rows", () => {
    expect(crimes).toHaveLength(2);
    expect(crimes[1].cat).toBe("burglary");
    expect(crimes[0].pos).toEqual([80.1, 13.0]);
    expect(decodeCrimes(null)).toEqual([]);
  });
  const ids = (f: CrimeFilter) => crimes.filter((c: MapCrime) => passes(c, f)).map((c) => c.id);
  it("filters by category, clock, linked, series and station", () => {
    expect(ids(base)).toEqual(["A", "B"]);
    expect(ids({ ...base, cats: new Set<CatKey>(["robbery"]) })).toEqual(["A"]);
    expect(ids({ ...base, clock: [19 * 60, 23 * 60] })).toEqual(["A"]);
    expect(ids({ ...base, linkedOnly: true })).toEqual(["A"]);
    expect(ids({ ...base, seriesOnly: true })).toEqual(["A"]);
    expect(ids({ ...base, stations: new Set(["PS-VELACHERY-J7"]) })).toEqual(["B"]);
    expect(ids({ ...base, from: Date.UTC(2026, 9, 10) })).toEqual(["B"]);
  });
});

describe("misc", () => {
  it("monthWindows covers the range newest first", () => {
    const w = monthWindows(Date.UTC(2026, 7, 15), Date.UTC(2026, 9, 3));
    expect(w).toHaveLength(3);
    expect(new Date(w[0][0]).getUTCMonth()).toBe(9);
    expect(new Date(w[2][0]).getUTCMonth()).toBe(7);
  });
  it("hhmm formats and wraps", () => {
    expect(hhmm(19 * 60)).toBe("19:00");
    expect(hhmm(1440 + 5)).toBe("00:05");
  });
});

import { isoWeek, seriesLabel, weekInRange } from "../pulse";

describe("isoWeek", () => {
  it("matches ISO-8601 including year boundaries", () => {
    expect(isoWeek(Date.UTC(2026, 9, 26, 6), 330)).toBe("2026-W44"); // Mon 26 Oct 2026
    expect(isoWeek(Date.UTC(2021, 0, 1, 6), 0)).toBe("2020-W53"); // Fri 1 Jan 2021
    expect(isoWeek(Date.UTC(2024, 11, 30, 6), 0)).toBe("2025-W01"); // Mon 30 Dec 2024
  });
  it("uses the city offset near midnight", () => {
    // Sunday 25 Oct 2026 20:00 UTC is Monday 01:30 IST
    expect(isoWeek(Date.UTC(2026, 9, 25, 20), 330)).toBe("2026-W44");
    expect(isoWeek(Date.UTC(2026, 9, 25, 20), 0)).toBe("2026-W43");
  });
  it("compares week labels", () => {
    expect(weekInRange("2026-W43", "2026-W40", "2026-W44")).toBe(true);
    expect(weekInRange("2026-W39", "2026-W40", "2026-W44")).toBe(false);
  });
});

describe("boundsOf", () => {
  it("wraps the points with padding", () => {
    const b = boundsOf([[80.25, 13.0], [80.22, 12.98]], 0.01)!;
    [80.21, 12.97, 80.26, 13.01].forEach((v, i) => expect(b[i]).toBeCloseTo(v, 6));
  });
  it("gives a single point an area and nothing for no points", () => {
    const b = boundsOf([[80.25, 13.0]], 0.02)!;
    [80.23, 12.98, 80.27, 13.02].forEach((v, i) => expect(b[i]).toBeCloseTo(v, 6));
    expect(boundsOf([])).toBeNull();
  });
});

// =====================
// DASH-04 filters (station, zone, status, weapon, vehicle, MO tag)
// =====================

describe("zoneStations", () => {
  const st = [{ id: "PS-ADYAR-J2", zone: "Adyar" }, { id: "PS-VELACHERY-J7", zone: "Adyar" }, { id: "PS-GUINDY-J3", zone: "Alandur" }, { id: "PS-X", zone: null }];
  it("expands zones to their stations; a station without a zone is in Unknown", () => {
    expect(Array.from(zoneStations(st, new Set(["Adyar"]))).sort()).toEqual(["PS-ADYAR-J2", "PS-VELACHERY-J7"]);
    expect(Array.from(zoneStations(st, new Set([UNKNOWN_ZONE])))).toEqual(["PS-X"]);
  });
  it("no zones selected means no restriction", () => {
    expect(zoneStations(st, new Set()).size).toBe(0);
  });
});

describe("decodeFacets", () => {
  it("reads a well-formed payload and lower-cases nothing it is not asked to", () => {
    const f = decodeFacets({ stations: [["PS-ADYAR-J2", "Adyar", "Adyar"], ["PS-X", "X", null]], weapon: { knife: ["C1", "C2"] }, vehicle: { motorcycle: ["C1"] }, mo: { "two wheeler from behind": ["C3"] } });
    expect(f.stations).toEqual([{ id: "PS-ADYAR-J2", name: "Adyar", zone: "Adyar" }, { id: "PS-X", name: "X", zone: null }]);
    expect(Array.from(f.weapon.get("knife") ?? [])).toEqual(["C1", "C2"]);
    expect(f.vehicle.get("motorcycle")?.has("C1")).toBe(true);
    expect(f.mo.get("two wheeler from behind")?.has("C3")).toBe(true);
  });
  it("survives junk and missing kinds", () => {
    for (const bad of [null, undefined, 42, "x", [], { weapon: "nope", mo: { t: "notarray" }, stations: [[1, 2]] }]) {
      const f = decodeFacets(bad);
      expect(f.weapon.size + f.vehicle.size + f.mo.size).toBe(0);
      expect(Array.isArray(f.stations)).toBe(true);
    }
  });
});

describe("facetIds", () => {
  const f = decodeFacets({ weapon: { knife: ["A", "B"], cutter: ["C"] }, vehicle: { motorcycle: ["A", "C", "D"] }, mo: { grille: ["C", "E"] } });
  it("is null when nothing is selected (no restriction)", () => {
    expect(facetIds(f, { weapon: new Set(), vehicle: new Set(), mo: new Set() })).toBeNull();
  });
  it("ORs within a kind and ANDs across kinds", () => {
    expect(Array.from(facetIds(f, { weapon: new Set(["knife", "cutter"]), vehicle: new Set(), mo: new Set() })!).sort()).toEqual(["A", "B", "C"]);
    expect(Array.from(facetIds(f, { weapon: new Set(["knife", "cutter"]), vehicle: new Set(["motorcycle"]), mo: new Set() })!).sort()).toEqual(["A", "C"]);
    expect(Array.from(facetIds(f, { weapon: new Set(["cutter"]), vehicle: new Set(["motorcycle"]), mo: new Set(["grille"]) })!)).toEqual(["C"]);
  });
  it("an unknown value matches nothing rather than everything", () => {
    expect(facetIds(f, { weapon: new Set(["sword"]), vehicle: new Set(), mo: new Set() })!.size).toBe(0);
  });
});

describe("passes with DASH-04 filters", () => {
  const c = decodeCrimes({ t: [1000], id: ["A"], st: ["PS-ADYAR-J2"], cat: ["robbery"], sub: ["chain_snatching"], lat: [13], lon: [80.2], mod: [1200], sev: [3], linked: [false], series: [null], status: ["registered"] })[0];
  const base: CrimeFilter = { cats: new Set(["robbery"] as CatKey[]), from: 0, to: 2000, clock: null, linkedOnly: false, seriesOnly: false, stations: new Set(), statuses: new Set(), ids: null };
  it("empty filters let everything through", () => {
    expect(passes(c, base)).toBe(true);
  });
  it("station, status and facet ids each restrict", () => {
    expect(passes(c, { ...base, stations: new Set(["PS-VELACHERY-J7"]) })).toBe(false);
    expect(passes(c, { ...base, statuses: new Set(["closed_undetected"]) })).toBe(false);
    expect(passes(c, { ...base, ids: new Set(["B"]) })).toBe(false);
    expect(passes(c, { ...base, stations: new Set(["PS-ADYAR-J2"]), statuses: new Set(["registered"]), ids: new Set(["A"]) })).toBe(true);
  });
});

describe("byCount", () => {
  it("orders facet values by crime count, ties alphabetical", () => {
    const m = new Map([["6th_street", new Set(["A"])], ["two_wheeler_from_behind", new Set(["A", "B", "C"])], ["night", new Set(["A", "B"])], ["gold_chain", new Set(["C", "D"])]]);
    expect(byCount(m)).toEqual(["two_wheeler_from_behind", "gold_chain", "night", "6th_street"]);
    expect(byCount(new Map())).toEqual([]);
  });
});

describe("initialFrame", () => {
  it("frames the visible crimes plus their arc ends and series members", () => {
    const b = initialFrame([[80.25, 13.0], [80.26, 13.01]], [[80.22, 12.98]], 0)!;
    expect(b).toEqual([80.22, 12.98, 80.26, 13.01]);
  });
  it("trims far outliers in a big set but never drops a linked point", () => {
    const pts: [number, number][] = Array.from({ length: 100 }, (_, i) => [80.2 + i * 0.001, 13.0 + i * 0.001]);
    pts.push([79.0, 12.0]); // a stray geocode
    const b = initialFrame(pts, [[80.5, 13.2]], 0)!;
    expect(b[0]).toBeGreaterThan(79.5);
    expect(b[2]).toBe(80.5);
    expect(b[3]).toBe(13.2);
  });
  it("is null when there is nothing to frame", () => {
    expect(initialFrame([], [])).toBeNull();
  });
});

describe("overlayPadding", () => {
  const box = { left: 0, top: 0, right: 1500, bottom: 900 };
  it("pads the side each panel hugs: chips top, panel right, dial left, scrubber bottom", () => {
    const p = overlayPadding(box, [
      { left: 12, top: 12, right: 900, bottom: 100 }, // chips + status line
      { left: 1200, top: 12, right: 1450, bottom: 600 }, // layers panel
      { left: 12, top: 530, right: 220, bottom: 740 }, // clock dial
      { left: 12, top: 750, right: 1488, bottom: 888 }, // scrubber
    ], 16);
    expect(p).toEqual({ top: 116, right: 316, left: 236, bottom: 166 });
  });
  it("ignores panels outside the map and keeps a usable frame on a phone", () => {
    const phone = { left: 0, top: 0, right: 350, bottom: 660 };
    const p = overlayPadding(phone, [
      { left: 12, top: 12, right: 300, bottom: 50 },
      { left: 12, top: 440, right: 338, bottom: 650 },
      { left: 400, top: 0, right: 500, bottom: 100 },
    ], 12);
    expect(p.top).toBe(62);
    expect(p.bottom).toBe(232);
    expect(phone.right - p.left - p.right).toBeGreaterThanOrEqual(350 * 0.4);
    expect(phone.bottom - p.top - p.bottom).toBeGreaterThanOrEqual(660 * 0.4);
  });
});

describe("seriesLabel", () => {
  it("does not repeat a station count the series name already carries", () => {
    expect(seriesLabel("Red two-wheeler chain snatchings · 3 stations", 9, 3)).toBe("Red two-wheeler chain snatchings · 3 stations · 9 cases");
  });
  it("adds the station count when the name has none, with singulars", () => {
    expect(seriesLabel("Night burglaries", 4, 2)).toBe("Night burglaries · 4 cases · 2 stations");
    expect(seriesLabel("One-off", 1, 1)).toBe("One-off · 1 case · 1 station");
  });
});
