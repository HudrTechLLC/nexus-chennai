import { describe, expect, it } from "vitest";
import { accessForPath, allows, canDecideAlerts, isRole, navFor } from "../roles";

const ALL = ["station_officer", "analyst", "supervisor", "admin"] as const;

describe("allows", () => {
  it("denies when there is no role", () => {
    expect(allows(null, "all")).toBe(false);
    expect(allows(undefined, "all")).toBe(false);
  });
  it("lets every police role open 'all' screens", () => {
    for (const r of ALL) expect(allows(r, "all")).toBe(true);
  });
  it("applies analyst+, supervisor+ and admin", () => {
    expect(allows("station_officer", "analyst+")).toBe(false);
    expect(allows("analyst", "analyst+")).toBe(true);
    expect(allows("analyst", "supervisor+")).toBe(false);
    expect(allows("supervisor", "supervisor+")).toBe(true);
    expect(allows("supervisor", "admin")).toBe(false);
    expect(allows("admin", "admin")).toBe(true);
  });
  it("supports explicit role lists", () => {
    expect(allows("station_officer", ["station_officer"])).toBe(true);
    expect(allows("analyst", ["station_officer"])).toBe(false);
  });
});

describe("canDecideAlerts", () => {
  it("station officers read only; analyst, supervisor and admin decide", () => {
    expect(canDecideAlerts("station_officer")).toBe(false);
    expect(canDecideAlerts("analyst")).toBe(true);
    expect(canDecideAlerts("supervisor")).toBe(true);
    expect(canDecideAlerts("admin")).toBe(true);
  });
});

describe("navFor", () => {
  it("shows link alerts to every police role", () => {
    for (const r of ALL) expect(navFor(r).map((n) => n.href)).toContain("/console/alerts");
  });
  it("hides graph, memory, stations, system and admin from station officers", () => {
    const hrefs = navFor("station_officer").map((n) => n.href);
    for (const h of ["/console/graph", "/console/memory", "/console/stations", "/console/system", "/console/admin"])
      expect(hrefs).not.toContain(h);
  });
  it("shows system only to admin", () => {
    expect(navFor("supervisor").map((n) => n.href)).not.toContain("/console/system");
    expect(navFor("admin").map((n) => n.href)).toContain("/console/system");
  });
});

describe("accessForPath", () => {
  it("maps nested paths to their section", () => {
    expect(accessForPath("/console/system/trace/run_1")).toBe("admin");
    expect(accessForPath("/console/graph")).toBe("analyst+");
    expect(accessForPath("/console/alerts/LA-2026-000913")).toBe("all");
  });
  it("limits FIR capture to station officers and admin", () => {
    expect(allows("analyst", accessForPath("/console/cases/new"))).toBe(false);
    expect(allows("station_officer", accessForPath("/console/cases/new"))).toBe(true);
  });
});

describe("isRole", () => {
  it("accepts only the four police roles", () => {
    expect(isRole("analyst")).toBe(true);
    expect(isRole("public")).toBe(false);
    expect(isRole(null)).toBe(false);
  });
});
