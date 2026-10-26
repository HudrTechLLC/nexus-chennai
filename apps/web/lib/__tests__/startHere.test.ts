import { describe, expect, it } from "vitest";
import { HERO_ALERT_ID, HERO_SERIES_ID, heroSteps, startHereMode, stationPending, WHAT_NEXUS_DOES } from "../startHere";
import type { AlertRow } from "../overview";

const alert = (alert_id: string, stations: string[], status = "pending", created_at = "2026-10-26T10:00:00Z"): AlertRow => ({
  alert_id, kind: "pair", stations, status, skeptic: null, created_at,
});

describe("startHereMode", () => {
  it("guides analysts and up, shows the station queue to officers", () => {
    expect(startHereMode("analyst")).toBe("guide");
    expect(startHereMode("supervisor")).toBe("guide");
    expect(startHereMode("admin")).toBe("guide");
    expect(startHereMode("station_officer")).toBe("station");
  });
});

describe("heroSteps", () => {
  it("links the hero alert and series when they exist", () => {
    const s = heroSteps({ heroAlert: { alert_id: HERO_ALERT_ID }, heroSeries: { series_id: HERO_SERIES_ID, name: "Red two-wheeler chain snatchings" } });
    expect(s.map((x) => x.href)).toEqual(["/console/alerts", `/console/alerts/${HERO_ALERT_ID}`, `/console/series/${HERO_SERIES_ID}`]);
    expect(s[2].body).toMatch(/^Red two-wheeler chain snatchings:/);
  });
  it("falls back to the list pages when a hero row is missing (never a 404)", () => {
    const s = heroSteps({ heroAlert: null, heroSeries: null });
    expect(s.map((x) => x.href)).toEqual(["/console/alerts", "/console/alerts", "/console/series"]);
    expect(s[1].body).toMatch(/not in this database/);
  });
  it("says a person decides", () => {
    expect(WHAT_NEXUS_DOES).toMatch(/A person decides/);
  });
});

describe("stationPending", () => {
  it("lists only pending alerts touching the station, newest first, capped", () => {
    const rows = [
      alert("LA-1", ["PS-A", "PS-B"], "pending", "2026-10-26T09:00:00Z"),
      alert("LA-2", ["PS-A"], "approved"),
      alert("LA-3", ["PS-C"]),
      alert("LA-4", ["PS-B", "PS-A"], "pending", "2026-10-26T11:00:00Z"),
      ...Array.from({ length: 6 }, (_, i) => alert(`LA-X${i}`, ["PS-A"], "pending", "2026-10-25T00:00:00Z")),
    ];
    const out = stationPending(rows, "PS-A");
    expect(out.total).toBe(8);
    expect(out.rows).toHaveLength(5);
    expect(out.rows.slice(0, 2).map((r) => r.alert_id)).toEqual(["LA-4", "LA-1"]);
  });
  it("is empty for an officer without a station", () => {
    expect(stationPending([alert("LA-1", ["PS-A"])], null)).toEqual({ rows: [], total: 0 });
  });
});
