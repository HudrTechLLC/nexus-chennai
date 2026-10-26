/**
 * Unit tests for the command overview helpers (lib/overview.ts, DASH-07).
 */
import { describe, expect, it } from "vitest";
import { alertFunnel, approvalRate, briefing, istIsoWeek, istMidnight, topSeries, weekKpis, type AlertRow } from "../overview";

const NOW = new Date("2026-10-26T12:00:00Z"); // 17:30 IST, Monday 26 Oct
const alert = (id: string, at: string, over: Partial<AlertRow> = {}): AlertRow => ({
  alert_id: id, kind: "pair", stations: ["PS-A"], status: "pending", skeptic: { verdict: "approved" }, created_at: at, ...over,
});

describe("IST day and week", () => {
  it("finds 00:00 IST, including just after midnight IST", () => {
    expect(istMidnight(NOW).toISOString()).toBe("2026-10-25T18:30:00.000Z");
    expect(istMidnight(new Date("2026-10-25T18:45:00Z")).toISOString()).toBe("2026-10-25T18:30:00.000Z"); // 00:15 IST on the 26th
    expect(istMidnight(new Date("2026-10-25T18:15:00Z")).toISOString()).toBe("2026-10-24T18:30:00.000Z"); // 23:45 IST on the 25th
  });
  it("labels the ISO week the way tips store it", () => {
    expect(istIsoWeek(NOW)).toBe("2026-W44");
    expect(istIsoWeek(new Date("2026-10-25T17:00:00Z"))).toBe("2026-W43"); // Sunday 22:30 IST
    expect(istIsoWeek(new Date("2027-01-01T06:00:00Z"))).toBe("2026-W53");
  });
});

describe("KPIs", () => {
  const alerts = [
    alert("A1", "2026-10-26T09:00:00Z", { stations: ["PS-A", "PS-B"] }),
    alert("A2", "2026-10-21T09:00:00Z", { stations: ["PS-A", "PS-A"] }), // same station twice is not cross-station
    alert("A3", "2026-10-10T09:00:00Z", { stations: ["PS-A", "PS-C"], status: "approved" }), // older than 7 days
    alert("A4", "2026-10-26T10:00:00Z", { status: "rejected", skeptic: { verdict: "needs_revision" } }),
  ];
  it("counts new and cross-station alerts in the last 7 days", () => {
    expect(weekKpis(alerts, NOW)).toEqual({ newAlerts: 3, crossStation: 1 });
  });
  it("shows no rate when nothing is decided, never 0%", () => {
    expect(approvalRate([alert("x", NOW.toISOString())])).toEqual({ approved: 0, rejected: 0, rate: null });
    expect(approvalRate(alerts)).toEqual({ approved: 1, rejected: 1, rate: 0.5 });
  });
  it("builds the raised → Skeptic → analyst funnel", () => {
    expect(alertFunnel(alerts)).toEqual({ raised: 4, skepticApproved: 3, analystApproved: 1 });
  });
});

describe("topSeries", () => {
  it("orders by member count and leaves closed series out", () => {
    const series = [
      { series_id: "S1", name: "Red Pulsar", status: "confirmed", created_at: null },
      { series_id: "S2", name: "Alpha", status: "candidate", created_at: null },
      { series_id: "S3", name: "Old", status: "closed", created_at: null },
    ];
    const members = [{ series_id: "S1" }, { series_id: "S1" }, { series_id: "S2" }, { series_id: "S3" }, { series_id: "S3" }, { series_id: "S3" }];
    expect(topSeries(series, members).map((s) => [s.series_id, s.members])).toEqual([["S1", 2], ["S2", 1]]);
    expect(topSeries([], [])).toEqual([]);
  });
});

describe("briefing", () => {
  it("says so when every count is 0", () => {
    const lines = briefing({ alerts: [], firsToday: 0, tipsThisWeek: 0, series: [], decisions: [], now: NOW });
    expect(lines.map((l) => l.text)).toEqual([
      "No new link alerts today.",
      "No FIRs registered today.",
      "No tips received this week (tips record only the week, to protect tipsters).",
      "No new series today.",
      "No alert decisions today.",
    ]);
    expect(lines.every((l) => l.href.startsWith("/console/"))).toBe(true);
  });
  it("counts only since 00:00 IST", () => {
    const lines = briefing({
      alerts: [
        alert("A1", "2026-10-25T19:00:00Z", { stations: ["PS-A", "PS-B"] }), // 00:30 IST today
        alert("A2", "2026-10-25T18:00:00Z"), // 23:30 IST yesterday
      ],
      firsToday: 1,
      tipsThisWeek: 2,
      series: [{ series_id: "S1", name: "x", status: "candidate", created_at: "2026-10-26T01:00:00Z" }],
      decisions: [{ at: "2026-10-26T02:00:00Z", decision: "approve" }, { at: "2026-10-26T03:00:00Z", decision: "reject" }, { at: "2026-10-20T03:00:00Z", decision: "reject" }],
      now: NOW,
    });
    expect(lines.map((l) => l.text)).toEqual([
      "1 new link alert today, 1 cross-station.",
      "1 FIR registered today.",
      "2 tips received this week (tips record only the week, to protect tipsters).",
      "1 new series today.",
      "2 alert decisions today: 1 approved, 1 rejected.",
    ]);
  });
});
