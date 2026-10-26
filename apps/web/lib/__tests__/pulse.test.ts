import { describe, expect, it } from "vitest";
import {
  arcPath, binDaily, binHours, catKey, cone, convexHull, decodeCrimes, DAY_MS, hhmm, inClockArc, km, localDay,
  monthWindows, padRing, passes, pulseTier, tzOffsetMinutes, type CatKey, type CrimeFilter, type MapCrime,
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
