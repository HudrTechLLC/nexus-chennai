/**
 * Unit tests for who may open a run trace (chief, 2026-10-27): analysts and supervisors see case, batch and
 * sweep runs; tip and search runs stay admin-only; station officers are denied; admins see everything.
 */

import { describe, expect, it } from "vitest";
import { canOpenTrace, traceAccess } from "../trace";

describe("traceAccess", () => {
  it("lets an analyst open the hero alert's case run", () => {
    expect(traceAccess("analyst", { kind: "case", run_id: "run_866f913f" })).toBe("ok");
    expect(traceAccess("supervisor", { kind: "batch", run_id: "run_1" })).toBe("ok");
    expect(traceAccess("analyst", { kind: "sweep", run_id: "run_2" })).toBe("ok");
  });

  it("hides tip, search and unknown runs from analysts and supervisors", () => {
    expect(traceAccess("analyst", { kind: "tip", run_id: "run_3" })).toBe("not_found");
    expect(traceAccess("supervisor", { kind: "search", run_id: "ask_69b79888" })).toBe("not_found");
    expect(traceAccess("analyst", null)).toBe("not_found");
  });

  it("hides source-onboarding runs (kind batch, admin-only area) from analysts and supervisors", () => {
    expect(traceAccess("analyst", { kind: "batch", run_id: "onboard_47e4e324" })).toBe("not_found");
    expect(traceAccess("supervisor", { kind: "batch", run_id: "onboard_47e4e324" })).toBe("not_found");
    expect(traceAccess("admin", { kind: "batch", run_id: "onboard_47e4e324" })).toBe("ok");
  });

  it("denies station officers and signed-out viewers whatever the run", () => {
    expect(traceAccess("station_officer", { kind: "case", run_id: "run_866f913f" })).toBe("denied");
    expect(traceAccess(null, { kind: "case", run_id: "run_866f913f" })).toBe("denied");
  });

  it("leaves admins unchanged: every kind, and a run with no row", () => {
    for (const kind of ["case", "batch", "sweep", "tip", "search"]) expect(traceAccess("admin", { kind, run_id: "run_4" })).toBe("ok");
    expect(traceAccess("admin", null)).toBe("ok");
  });
});

describe("canOpenTrace (links)", () => {
  it("matches the page rule so no link leads to a denied page", () => {
    expect(canOpenTrace("analyst", "case")).toBe(true);
    expect(canOpenTrace("analyst", "tip")).toBe(false);
    expect(canOpenTrace("analyst", undefined)).toBe(false);
    expect(canOpenTrace("station_officer", "case")).toBe(false);
    expect(canOpenTrace("admin", "search")).toBe(true);
  });
});
