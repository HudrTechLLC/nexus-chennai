/**
 * Unit tests for the vehicles register helpers (lib/vehicles.ts, CAP-06).
 */
import { describe, expect, it } from "vitest";
import { groupVehicles, hasVehicleFilter, parseVehicleFilters, readsPerPlate, type VehicleRow } from "../vehicles";

const row = (crime: string, plate: string | null, over: Partial<VehicleRow> = {}): VehicleRow => ({
  crime_id: crime, plate_pattern: plate, vehicle_type: "motorcycle", make_model: "Bajaj Pulsar", colour: "red", role: "used_by_offender", ...over,
});

describe("parseVehicleFilters", () => {
  it("keeps valid filters and normalises the plate", () => {
    expect(parseVehicleFilters({ plate: "tn 09 ** 4471", type: "Car", make: "Swift", colour: "white" }))
      .toEqual({ plate: "TN09??4471", type: "car", make: "swift", colour: "white" });
  });
  it("drops anything that is not a plain word or a known type", () => {
    const f = parseVehicleFilters({ plate: "%_", type: "spaceship", make: "a%b", colour: "x" });
    expect(f).toEqual({ plate: null, type: null, make: null, colour: null });
    expect(hasVehicleFilter(f)).toBe(false);
  });
});

describe("groupVehicles", () => {
  it("makes one entry per recorded plate with all its cases, most cases first", () => {
    const g = groupVehicles([
      row("C1", "TN09AB4471"), row("C2", "tn09ab4471", { role: "stolen" }), row("C3", "TN02??9867"),
      row("C1", "TN09AB4471"), // the same vehicle twice on one case counts once
    ]);
    expect(g.map((x) => [x.plate, x.crimes, x.roles])).toEqual([
      ["TN09AB4471", ["C1", "C2"], ["stolen", "used_by_offender"]],
      ["TN02??9867", ["C3"], ["used_by_offender"]],
    ]);
  });
  it("keeps vehicles with no plate as separate entries, after the plated ones", () => {
    const g = groupVehicles([row("C1", null), row("C2", null), row("C3", "TN01X1")]);
    expect(g.map((x) => x.plate)).toEqual(["TN01X1", null, null]);
  });
  it("describes a plate by its most common make and colour", () => {
    const g = groupVehicles([row("C1", "P1", { colour: "red" }), row("C2", "P1", { colour: "red" }), row("C3", "P1", { colour: "maroon" })]);
    expect(g[0].colour).toBe("red");
  });
});

describe("readsPerPlate", () => {
  it("counts ANPR reads per exact plate", () => {
    expect(Object.fromEntries(readsPerPlate([{ plate_text: "TN09AB4471" }, { plate_text: "tn09 ab4471" }, { plate_text: "TN01X1" }])))
      .toEqual({ TN09AB4471: 2, TN01X1: 1 });
  });
});
