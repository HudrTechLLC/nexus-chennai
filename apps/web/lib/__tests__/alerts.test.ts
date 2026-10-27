import { describe, expect, it } from "vitest";
import {
  coverageCap, coverageCapLine, parseScope,
  coverageOf, decisionState, factorRows, latestDecision, parseSort, parseTab, queryIds, sortAlerts,
  validateDecision, type AlertDecision, type LinkFactor,
} from "../alerts";

const f = (factor: LinkFactor["factor"], weight: number, value: number, extra: Partial<LinkFactor> = {}): LinkFactor => ({
  alert_id: "LA-1", factor, weight, value, evidence: [], reason: "r", struck_by_skeptic: false, ...extra,
});
const dec = (at: string, extra: Partial<AlertDecision> = {}): AlertDecision => ({
  decision_id: 1, alert_id: "LA-1", decision: "approve", reason_code: null, note: null, by: "u", at, processed_at: null, ...extra,
});

describe("factorRows", () => {
  it("orders by weight and zeroes struck factors", () => {
    const rows = factorRows([f("weapon_tool", 0.08, 1, { struck_by_skeptic: true }), f("mo_similarity", 0.25, 0.91), f("vehicle", 0.15, 0.88)]);
    expect(rows.map((r) => r.factor)).toEqual(["mo_similarity", "vehicle", "weapon_tool"]);
    expect(rows[0].contribution).toBeCloseTo(0.2275);
    expect(rows[2].contribution).toBe(0);
    expect(rows[0].label).toBe("MO similarity");
  });
});

describe("coverageOf", () => {
  it("prefers the stored column", () => {
    expect(coverageOf({ coverage: 0.6, link_factors: [f("mo_similarity", 0.25, 1)] })).toBe(0.6);
  });
  it("sums present factor weights otherwise", () => {
    expect(coverageOf({ link_factors: [f("mo_similarity", 0.25, 1), f("vehicle", 0.15, 0)] })).toBe(0.4);
  });
});

describe("queryIds", () => {
  it("collects distinct ids and skips evidence without one", () => {
    const ids = queryIds([
      f("vehicle", 0.15, 1, { evidence: [{ view: "v", row: "a", query_id: "q1" }, { view: "v", row: "b" }] }),
      f("mo_similarity", 0.25, 1, { evidence: [{ view: "v", row: "c", query_id: "q1" }, { view: "v", row: "d", query_id: "q2" }] }),
    ]);
    expect(ids).toEqual(["q1", "q2"]);
  });
});

describe("validateDecision", () => {
  it("accepts a plain approval", () => expect(validateDecision({ decision: "approve" })).toBeNull());
  it("requires a reason to reject", () => expect(validateDecision({ decision: "reject" })).toMatch(/reason/));
  it("rejects unknown reasons", () => expect(validateDecision({ decision: "reject", reason_code: "nope" })).toMatch(/Unknown/));
  it("requires a note for Other", () => {
    expect(validateDecision({ decision: "reject", reason_code: "other", note: " " })).toMatch(/note/);
    expect(validateDecision({ decision: "reject", reason_code: "other", note: "different gang" })).toBeNull();
  });
});

describe("decisions", () => {
  it("latestDecision picks the newest", () => {
    expect(latestDecision([dec("2026-10-26T10:00:00Z"), dec("2026-10-26T12:00:00Z", { decision_id: 2 })])?.decision_id).toBe(2);
    expect(latestDecision([])).toBeNull();
  });
  it("shows awaiting_worker between a decision and the worker applying it", () => {
    expect(decisionState({ status: "pending", alert_decisions: [] })).toBe("pending");
    expect(decisionState({ status: "pending", alert_decisions: [dec("2026-10-26T10:00:00Z")] })).toBe("awaiting_worker");
    expect(decisionState({ status: "rejected", alert_decisions: [dec("2026-10-26T10:00:00Z")] })).toBe("rejected");
  });
});

describe("tabs and sorting", () => {
  it("falls back to safe defaults", () => {
    expect(parseTab("rejected")).toBe("rejected");
    expect(parseTab("drop table")).toBe("pending");
    expect(parseSort(undefined)).toBe("score");
  });
  it("sorts by score, newest and number of stations", () => {
    const rows = [
      { alert_id: "a", score: 0.6, created_at: "2026-10-26T10:00:00Z", stations: ["X"] },
      { alert_id: "b", score: 0.9, created_at: "2026-10-25T10:00:00Z", stations: ["X", "Y"] },
      { alert_id: "c", score: 0.7, created_at: "2026-10-27T10:00:00Z", stations: ["Z"] },
    ];
    expect(sortAlerts(rows, "score").map((r) => r.alert_id)).toEqual(["b", "c", "a"]);
    expect(sortAlerts(rows, "newest").map((r) => r.alert_id)).toEqual(["c", "a", "b"]);
    expect(sortAlerts(rows, "stations")[0].alert_id).toBe("b");
  });
});

describe("coverageCap (D-016)", () => {
  const f = (factor: string, weight: number, value: number | null, struck = false) =>
    ({ alert_id: "A", factor, weight, value, evidence: [], reason: "", struck_by_skeptic: struck }) as never;
  const capped = { band: "medium" as const, score: 1, coverage: 0.35,
    link_factors: [f("space_time", 0.2, 1), f("mo_similarity", 0.15, 1), f("vehicle", 0.15, 0, true)] };

  it("explains a high score held at medium by low coverage", () => {
    expect(coverageCap(capped)).toEqual({ withData: 2, total: 9, coverage: 0.35 });
    expect(coverageCapLine(capped)).toBe("Held as a lead for analyst review: only 2 of 9 factors had data (coverage 35%)");
  });
  it("says nothing when the score was medium on its own merits", () => {
    expect(coverageCapLine({ ...capped, score: 0.7 })).toBeNull();
  });
  it("says nothing when coverage was enough or the band is high", () => {
    expect(coverageCapLine({ ...capped, coverage: 0.5 })).toBeNull();
    expect(coverageCapLine({ ...capped, band: "high" })).toBeNull();
  });
  it("forensic matches are exempt from the cap", () => {
    expect(coverageCapLine({ ...capped, link_factors: [...capped.link_factors, f("forensic", 0.1, 1)] })).toBeNull();
  });
});

describe("parseScope (officer inbox defaults to own station)", () => {
  it("station officers open on their station and can switch to city-wide", () => {
    expect(parseScope(undefined, "station_officer", "PS-ADYAR-J2")).toBe("station");
    expect(parseScope("city", "station_officer", "PS-ADYAR-J2")).toBe("city");
    expect(parseScope("junk", "station_officer", "PS-ADYAR-J2")).toBe("station");
  });
  it("other roles, or an officer without a station, always see city-wide", () => {
    expect(parseScope("station", "analyst", null)).toBe("city");
    expect(parseScope("station", "supervisor", "PS-ADYAR-J2")).toBe("city");
    expect(parseScope(undefined, "station_officer", null)).toBe("city");
  });
});
