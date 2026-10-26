/**
 * The console sidebar marks the right item active: the deepest matching section, Overview only on /console.
 */
import { describe, expect, it } from "vitest";
import { activeHref, NAV_ICONS } from "../ConsoleNav";
import { NAV } from "@/lib/roles";

describe("activeHref", () => {
  it("marks Overview only on /console itself", () => {
    expect(activeHref(NAV, "/console")).toBe("/console");
    expect(activeHref(NAV, "/console/alerts")).toBe("/console/alerts");
  });
  it("prefers the deepest section", () => {
    expect(activeHref(NAV, "/console/system/sources/onboard/abc")).toBe("/console/system/sources");
    expect(activeHref(NAV, "/console/system/trace/run_1")).toBe("/console/system");
    expect(activeHref(NAV, "/console/alerts/LA-2026-000913")).toBe("/console/alerts");
  });
  it("marks nothing for an unknown path", () => {
    expect(activeHref(NAV, "/console/nowhere")).toBeNull();
  });
});

describe("NAV_ICONS", () => {
  it("has an icon for every nav item", () => {
    for (const n of NAV) expect(NAV_ICONS[n.icon], n.icon).toBeTruthy();
  });
});
