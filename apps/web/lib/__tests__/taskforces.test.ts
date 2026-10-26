import { describe, expect, it } from "vitest";
import {
  abilities, canPropose, countByStatus, isTfStatus, parseCrimeIds, sortMembers, stationsSpanned, suggestedName, validateNote, validateProposal,
} from "../taskforces";

describe("abilities (mirror the 0004_06_03 RPCs)", () => {
  it("lets supervisors and admins approve proposals, and close active task forces", () => {
    for (const r of ["supervisor", "admin"] as const) {
      expect(abilities(r, "proposed", null)).toMatchObject({ approve: true, close: false, manageMembers: true, addNote: true, linkCases: true });
      expect(abilities(r, "active", null)).toMatchObject({ approve: false, close: true });
    }
  });

  it("never lets analysts or station officers decide or manage members", () => {
    for (const r of ["analyst", "station_officer"] as const) {
      for (const s of ["proposed", "active"] as const) {
        const a = abilities(r, s, null);
        expect(a.approve || a.close || a.manageMembers).toBe(false);
      }
    }
  });

  it("lets members note, and only leads link cases", () => {
    expect(abilities("station_officer", "active", "member")).toMatchObject({ addNote: true, linkCases: false });
    expect(abilities("station_officer", "active", "lead")).toMatchObject({ addNote: true, linkCases: true });
    expect(abilities("station_officer", "active", null)).toMatchObject({ addNote: false, linkCases: false });
    expect(abilities("analyst", "active", null).addNote).toBe(false);
  });

  it("freezes closed and declined task forces for everyone", () => {
    for (const s of ["closed", "declined"] as const) {
      const a = abilities("admin", s, "lead");
      expect(Object.values(a).some(Boolean)).toBe(false);
    }
  });

  it("lets analysts, supervisors and admins propose", () => {
    expect(canPropose("analyst")).toBe(true);
    expect(canPropose("supervisor")).toBe(true);
    expect(canPropose("station_officer")).toBe(false);
    expect(canPropose(null)).toBe(false);
  });
});

describe("validation (same limits as the RPCs)", () => {
  it("checks the name and purpose", () => {
    expect(validateProposal({ name: "ab" })).toMatch(/3–120/);
    expect(validateProposal({ name: "x".repeat(121) })).toMatch(/3–120/);
    expect(validateProposal({ name: "  Red Pulsar joint team  " })).toBeNull();
    expect(validateProposal({ name: "Joint team", purpose: "p".repeat(2001) })).toMatch(/2000/);
  });
  it("checks notes", () => {
    expect(validateNote("   ")).toMatch(/first/);
    expect(validateNote("n".repeat(2001))).toMatch(/2000/);
    expect(validateNote("CCTV from LB Road requested")).toBeNull();
  });
});

describe("parseCrimeIds", () => {
  it("splits, upper-cases, de-duplicates and drops junk", () => {
    expect(parseCrimeIds("chn-ad-2026-001182, CHN-VL-2026-000877\nCHN-AD-2026-001182 ;; x ' or 1=1")).toEqual(["CHN-AD-2026-001182", "CHN-VL-2026-000877"]);
    expect(parseCrimeIds("")).toEqual([]);
  });
});

describe("display helpers", () => {
  it("suggests a name from the source", () => {
    expect(suggestedName({ seriesName: "3 linked cases (PS-A, PS-B)" })).toBe("Joint task force · 3 linked cases (PS-A, PS-B)");
    expect(suggestedName({ alertId: "LA-1" })).toBe("Joint task force · LA-1");
    expect(suggestedName({})).toBe("");
    expect(suggestedName({ seriesName: "s".repeat(200) })).toHaveLength(120);
  });
  it("counts by status, including DASH-07's active count", () => {
    const c = countByStatus([{ status: "active" }, { status: "active" }, { status: "proposed" }, { status: "declined" }]);
    expect(c).toEqual({ all: 4, proposed: 1, active: 2, closed: 0, declined: 1 });
    expect(isTfStatus("active")).toBe(true);
    expect(isTfStatus("open")).toBe(false);
  });
  it("puts leads first, then sorts by name", () => {
    const rows = sortMembers([{ role: "member" as const, name: "Bala" }, { role: "lead" as const, name: "Zara" }, { role: "member" as const, name: "Anu" }]);
    expect(rows.map((r) => r.name)).toEqual(["Zara", "Anu", "Bala"]);
  });
  it("lists the stations a task force spans", () => {
    expect(stationsSpanned([{ station_id: "PS-B" }, { station_id: "PS-A" }, { station_id: "PS-B" }, { station_id: "" }])).toEqual(["PS-A", "PS-B"]);
  });
});
