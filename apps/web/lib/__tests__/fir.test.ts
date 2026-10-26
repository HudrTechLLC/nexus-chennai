/**
 * Unit tests for FIR capture (lib/fir.ts): time zones, location cells, validation, payload.
 */
import { describe, expect, it } from "vitest";
import { cityLocalToIso, emptyFir, geohash, inBounds, toPayload, tzOffsetMinutes, validateFir, type FirForm } from "../fir";

const TZ = "Asia/Kolkata";
const BOUNDS: [number, number, number, number] = [80.0, 12.8, 80.35, 13.25];
const NOW = new Date("2026-10-26T08:00:00Z");

const good = (over: Partial<FirForm> = {}): FirForm => ({
  ...emptyFir(),
  category: "robbery", sub_type: "chain_snatching", sections: ["BNS 304(2)"],
  occurred_from: "2026-10-26T10:40", occurred_to: "2026-10-26T10:45",
  lat: 12.997044, lon: 80.247108, address: "near a college, Adyar", severity: 3,
  narrative: "Two men on a red motorcycle snatched the complainant's chain.",
  vehicles: [{ role: "used_by_offender", vehicle_type: "motorcycle", plate_pattern: "TN 09 ?? 4471", make_model: "Bajaj Pulsar", colour: "red" }],
  statements: ["I saw a black helmet.", "  "],
  ...over,
});

describe("city time", () => {
  it("knows the zone offset", () => {
    expect(tzOffsetMinutes(TZ, NOW)).toBe(330);
    expect(tzOffsetMinutes("UTC", NOW)).toBe(0);
  });
  it("reads datetime-local input as city wall-clock time", () => {
    expect(cityLocalToIso("2026-10-26T10:40", TZ)).toBe("2026-10-26T05:10:00.000Z");
    expect(cityLocalToIso("2026-10-26 10:40", TZ)).toBeNull();
  });
});

describe("location cells", () => {
  it("matches the seed's geohash7 for the same point", () => {
    expect(geohash(12.997044, 80.247108, 7)).toBe("tf31fn4");
  });
  it("checks city bounds", () => {
    expect(inBounds(13.0, 80.25, BOUNDS)).toBe(true);
    expect(inBounds(19.07, 72.87, BOUNDS)).toBe(false);
  });
});

describe("validateFir", () => {
  const opts = { tz: TZ, bounds: BOUNDS, now: NOW };
  it("accepts a complete FIR", () => {
    expect(validateFir(good(), opts)).toEqual({});
  });
  it("flags each missing or wrong field", () => {
    const e = validateFir(good({ category: "arson", sections: [], occurred_from: "", lat: null, narrative: " ", severity: 9 }), opts);
    expect(Object.keys(e).sort()).toEqual(["category", "narrative", "occurred_from", "place", "sections", "severity"]);
  });
  it("rejects a sub-type from another category", () => {
    expect(validateFir(good({ sub_type: "car_theft" }), opts).sub_type).toBeDefined();
  });
  it("rejects future times, reversed ranges and places outside the city", () => {
    expect(validateFir(good({ occurred_from: "2026-10-26T18:00", occurred_to: "" }), opts).occurred_from).toMatch(/future/);
    expect(validateFir(good({ occurred_to: "2026-10-26T10:00" }), opts).occurred_to).toMatch(/before/);
    expect(validateFir(good({ lat: 19.07, lon: 72.87 }), opts).place).toMatch(/outside/);
  });
  it("checks plate characters and property values", () => {
    const e = validateFir(good({
      vehicles: [{ role: "stolen", vehicle_type: "car", plate_pattern: "TN%09", make_model: "", colour: "" }],
      property: [{ item: "chain", value_inr: "90,000" }],
    }), opts);
    expect(e["vehicles.0"]).toBeDefined();
    expect(e["property.0"]).toBeDefined();
  });
});

describe("toPayload", () => {
  it("builds the file_fir jsonb with cells, UTC times and trimmed lists", () => {
    const p = toPayload(good({ property: [{ item: "gold chain", value_inr: "90000" }, { item: " ", value_inr: "" }], offenders: [{ count: "2", build: "", age_band: "20-30", helmet: "black", clothing: "", marks: "" }] }), TZ);
    expect(p.occurred_from).toBe("2026-10-26T05:10:00.000Z");
    expect(p.h3_r8).toBe("88618c41b7fffff");
    expect(p.h3_r9).toMatch(/^89618c4/);
    expect(p.geohash7).toBe("tf31fn4");
    expect(p.statements).toEqual([{ text: "I saw a black helmet." }]);
    expect(p.property).toEqual([{ item: "gold chain", value_inr: 90000 }]);
    expect(p.offenders_described).toEqual([{ count: 2, age_band: "20-30", helmet: "black" }]);
    expect(p.vehicles[0].plate_pattern).toBe("TN 09 ?? 4471"); // the RPC normalises plates
    expect(p.tz).toBe(TZ);
    expect("station_id" in p).toBe(false);
  });
  it("passes station_id only when given (admin)", () => {
    expect(toPayload(good({ station_id: "PS-ADYAR-J2" }), TZ).station_id).toBe("PS-ADYAR-J2");
  });
});
