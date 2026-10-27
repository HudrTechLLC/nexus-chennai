import { describe, expect, it } from "vitest";
import { accessForPath, allows, canDecideAlerts, isRole, NAV, NAV_GROUPS, navFor } from "../roles";

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
  it("shows admin only to admin (WS3-14)", () => {
    for (const r of ALL.filter((x) => x !== "admin")) expect(navFor(r).map((n) => n.href)).not.toContain("/console/admin");
    expect(navFor("admin").map((n) => n.href)).toContain("/console/admin");
    expect(accessForPath("/console/admin")).toBe("admin");
  });
});

describe("accessForPath", () => {
  it("maps nested paths to their section", () => {
    expect(accessForPath("/console/system/trace/run_1")).toBe("analyst+");
    expect(accessForPath("/console/system")).toBe("admin");
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

describe("nav never links to a 404", () => {
  it("every visible nav item has a page under app/console/(app)", async () => {
    const { existsSync } = await import("node:fs");
    const { join } = await import("node:path");
    const root = join(__dirname, "..", "..", "app", "console", "(app)");
    const missing = NAV.filter((n) => !n.hidden)
      .map((n) => n.href.replace(/^\/console\/?/, ""))
      .filter((rel) => !existsSync(join(root, rel, "page.tsx")));
    expect(missing).toEqual([]);
  });
});

describe("grouped navigation", () => {
  const groups = NAV_GROUPS.map((g) => g.key);
  it("puts every item in a known group with an icon", () => {
    for (const n of NAV) {
      expect(groups).toContain(n.group);
      expect(n.icon).toMatch(/^[a-z]+$/);
    }
  });
  it("orders items group by group, so each sidebar section is one run", () => {
    const order = NAV.map((n) => groups.indexOf(n.group));
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });
  it("keeps every hub one click away for the roles that can open it", () => {
    expect(navFor("admin").map((n) => n.href)).toEqual(expect.arrayContaining(
      ["/console", "/console/map", "/console/alerts", "/console/series", "/console/cases", "/console/ask", "/console/system", "/console/system/sources", "/console/admin"]));
    expect(navFor("station_officer").map((n) => n.href)).toEqual(expect.arrayContaining(["/console", "/console/alerts", "/console/appeals", "/console/tips"]));
  });
  it("leaves Notifications out of the wide sidebar (the header bell links there)", () => {
    expect(NAV.find((n) => n.href === "/console/notifications")?.desktop).toBe("bell");
  });
});
