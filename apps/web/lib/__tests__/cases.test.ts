/**
 * Unit tests for the case list / case file helpers (lib/cases.ts).
 */
import { describe, expect, it } from "vitest";
import {
  buildTimeline, canWriteCase, casesHref, dayRange, describe as describeObj, maskPii, moCorrections, moRows, moToText,
  normaliseFir, normalisePlate, parseCaseFilters, plateIlike, plateMatches,
} from "../cases";

describe("parseCaseFilters", () => {
  it("keeps valid filters", () => {
    const f = parseCaseFilters({ station: "PS-ADYAR-J2", category: "robbery", status: "undetected", from: "2026-10-01", to: "2026-10-26", fir: "1182/2026", plate: "tn 09 ?? 4471", page: "3" });
    expect(f).toEqual({ station: "PS-ADYAR-J2", category: "robbery", status: "undetected", from: "2026-10-01", to: "2026-10-26", fir: "1182/2026", plate: "TN09??4471", page: 3 });
  });
  it("drops anything malformed instead of passing it to a query", () => {
    const f = parseCaseFilters({ station: "x'; drop", category: "arson", status: "lost", from: "1/10/2026", fir: "abc", plate: "%_", page: "-2" });
    expect(f).toEqual({ station: null, category: null, status: null, from: null, to: null, fir: null, plate: null, page: 1 });
  });
  it("takes the first value of a repeated param", () => {
    expect(parseCaseFilters({ category: ["theft", "robbery"] }).category).toBe("theft");
  });
});

describe("casesHref", () => {
  it("round-trips only set filters", () => {
    expect(casesHref({ station: "PS-ADYAR-J2", page: 2, fir: null })).toBe("/console/cases?station=PS-ADYAR-J2&page=2");
    expect(casesHref({ page: 1 })).toBe("/console/cases");
  });
});

describe("FIR and plate normalising", () => {
  it("accepts FIR numbers with or without year", () => {
    expect(normaliseFir("1182 / 2026")).toBe("1182/2026");
    expect(normaliseFir("877")).toBe("877");
    expect(normaliseFir("FIR-1")).toBeNull();
  });
  it("upper-cases plates, strips separators, turns * into ?", () => {
    expect(normalisePlate("tn-09 ab.4471")).toBe("TN09AB4471");
    expect(normalisePlate("TN 09 ** 4471")).toBe("TN09??4471");
    expect(normalisePlate("4%71")).toBeNull();
    expect(normalisePlate("TN")).toBeNull(); // too broad to narrow anything
    expect(normalisePlate("TN0")).toBe("TN0");
  });
});

describe("plate matching", () => {
  it("maps a typed ? to the one-character ILIKE wildcard", () => {
    expect(plateIlike("TN09??4471")).toBe("%TN09__4471%");
    expect(plateIlike("4471")).toBe("%4471%");
  });
  it("treats ? on either side as unknown", () => {
    expect(plateMatches("TN09??4471", "4471")).toBe(true);
    expect(plateMatches("TN09??4471", "09AB44")).toBe(true); // stored ? matches typed letters
    expect(plateMatches("TN09AB4471", "TN09??44")).toBe(true);
    expect(plateMatches("TN09AB4471", "TN10")).toBe(false);
    expect(plateMatches(null, "TN")).toBe(false);
  });
});

describe("dayRange", () => {
  it("turns city-time dates into an inclusive day window", () => {
    expect(dayRange("2026-10-01", "2026-10-01")).toEqual({ gte: "2026-09-30T18:30:00.000Z", lt: "2026-10-01T18:30:00.000Z" });
    expect(dayRange(null, null)).toEqual({ gte: null, lt: null });
  });
});

describe("canWriteCase", () => {
  it("mirrors can_write_crime", () => {
    expect(canWriteCase("station_officer", "PS-A", "PS-A")).toBe(true);
    expect(canWriteCase("station_officer", "PS-A", "PS-B")).toBe(false);
    expect(canWriteCase("analyst", "PS-A", "PS-A")).toBe(false);
    expect(canWriteCase("supervisor", null, "PS-B")).toBe(true);
    expect(canWriteCase("admin", null, "PS-B")).toBe(true);
  });
});

describe("maskPii", () => {
  it("masks phone and Aadhaar-like numbers, keeps FIR numbers and dates", () => {
    const out = maskPii("Call 98765 43210 or +91 9876543210; Aadhaar 1234 5678 9012. FIR 1182/2026 on 25-10-2026.");
    expect(out).not.toMatch(/98765|43210|9876543210|1234 5678 9012/);
    expect(out).toContain("FIR 1182/2026 on 25-10-2026");
  });
});

describe("display helpers", () => {
  it("describes descriptor objects and skips empties", () => {
    expect(describeObj({ build: "heavy", count: 1, helmet: null, marks: [] })).toBe("build: heavy · count: 1");
    expect(describeObj(null)).toBe("—");
  });
  it("flattens MO into sorted label rows", () => {
    expect(moRows({ violence: "none", approach: "cut_window_grille", disguise: [], target_item: "gold_jewellery_and_cash" })).toEqual([
      ["approach", "cut window grille"], ["target_item", "gold jewellery and cash"], ["violence", "none"],
    ]);
  });
  it("orders the timeline newest first and drops undated items", () => {
    const t = buildTimeline([
      { at: "2026-10-25T12:50:00Z", kind: "occurred", label: "a" },
      null,
      { at: "", kind: "diary", label: "skip" },
      { at: "2026-10-27T11:27:00Z", kind: "fir", label: "b" },
    ]);
    expect(t.map((x) => x.label)).toEqual(["b", "a"]);
  });
});

describe("moCorrections", () => {
  const mo = { approach: "two_wheeler_from_behind", offender_count: 2, disguise: ["helmet"], place_type: ["bus_stop"], verbal: null, violence: "push" };
  it("returns nothing when the officer changed nothing", () => {
    expect(moCorrections(mo, { approach: "two wheeler from behind", offender_count: "2", disguise: "helmet", verbal: "" })).toEqual({ corrections: {} });
  });
  it("returns only changed fields in the stored shape", () => {
    expect(moCorrections(mo, { violence: "Snatching", disguise: "black helmet, mask", offender_count: "3", place_type: "bus stop" })).toEqual({
      corrections: { violence: "snatching", disguise: ["black_helmet", "mask"], offender_count: 3 },
    });
  });
  it("can clear a field", () => {
    expect(moCorrections(mo, { violence: "" })).toEqual({ corrections: { violence: null } });
  });
  it("rejects a bad offender count", () => {
    expect(moCorrections(mo, { offender_count: "two" })).toHaveProperty("error");
  });
  it("shows values as text", () => {
    expect(moToText(["bus_stop", "main_road"])).toBe("bus stop, main road");
    expect(moToText(null)).toBe("");
  });
});
