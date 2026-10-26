/**
 * Unit tests for the Skeptic review helpers (WS3-26). Shapes from tonight's live traces.
 */
import { describe, expect, it } from "vitest";
import { alertTimeline, capFlipped, droppedLinks, pairKey, parseSkepticEvent, skepticSummary, skepticTraceFilter, type SkepticEventRow } from "../skeptic";

const ev = (seq: number, action: string, input: string | null, output: string | null, status = "ok", run = "run_1"): SkepticEventRow =>
  ({ run_id: run, seq, ts: `2026-10-26T20:${String(seq).padStart(2, "0")}:00+05:30`, action, input_summary: input, output_summary: output, status });

const HERO = ["CHN-VL-2026-000877", "CHN-AD-2026-001182"]; // case order, not sorted

describe("parseSkepticEvent", () => {
  it("reads a verdict: pair, round, score, struck list and critique", () => {
    const s = parseSkepticEvent(ev(1, "approve", "pair CHN-AD-2026-001182|CHN-VL-2026-000877 round 1",
      "score=0.7887 struck=['vehicle', \"mo\"] Strong link: near-identical MO."))!;
    expect(s).toMatchObject({ kind: "approve", pair: "CHN-AD-2026-001182|CHN-VL-2026-000877", round: 1, score: 0.7887,
      struck: ["vehicle", "mo"], text: "Strong link: near-identical MO." });
  });
  it("reads strike_factor, recheck_unavailable, critique_failed and critique_missing", () => {
    expect(parseSkepticEvent(ev(2, "strike_factor", "pair A-1|B-2 factor vehicle", "fresh=0 linker=1; score 0.71→0.58")))
      .toMatchObject({ kind: "strike", pair: "A-1|B-2", factor: "vehicle" });
    expect(parseSkepticEvent(ev(3, "recheck_unavailable", "A-1|B-2 corroboration q_news", "timed out", "degraded")))
      .toMatchObject({ kind: "unverified", pair: "A-1|B-2", factor: "corroboration" });
    expect(parseSkepticEvent(ev(4, "critique_failed", "3 pairs round 2", "code verdicts stand", "degraded")))
      .toMatchObject({ kind: "critique_failed", pair: null, round: 2 });
    expect(parseSkepticEvent(ev(5, "critique_missing", "A-1|B-2", "", "degraded"))).toMatchObject({ kind: "critique_missing", pair: "A-1|B-2" });
  });
  it("ignores other Skeptic events", () => {
    expect(parseSkepticEvent(ev(6, "zetaris_query", "q_case", "rows=1"))).toBeNull();
    expect(parseSkepticEvent(ev(7, "model_call", "lane=reason critique 1 pairs round 2", "61835 ms"))).toBeNull();
  });
});

describe("alertTimeline", () => {
  const rows = [
    ev(9, "approve", "pair CHN-AD-2026-001182|CHN-VL-2026-000877 round 2", "score=0.79 struck=[] fine"),
    ev(3, "send_back", "pair CHN-AD-2026-001182|CHN-VL-2026-000877 round 1", "score=0.72 struck=[] gap too long"),
    ev(4, "drop", "pair CHN-CM-2025-000450|CHN-CM-2025-000461 round 1", "score=0.69 struck=[] different types"),
    ev(2, "critique_failed", "2 pairs round 1", "code verdicts stand"),
    ev(6, "critique_failed", "2 pairs round 2", "other pairs' call"),
    ev(8, "critique_failed", "2 pairs round 2", "code verdicts stand"),
  ];
  it("matches the alert's crimes in any order to the sorted trace pair", () => {
    expect(pairKey(HERO)).toBe("CHN-AD-2026-001182|CHN-VL-2026-000877");
    expect(alertTimeline(rows, HERO, "applied").map((s) => [s.seq, s.kind])).toEqual([[3, "send_back"], [9, "approve"]]);
  });
  it("does not show other pairs' critique failures when this alert's critique was applied", () => {
    expect(alertTimeline(rows, HERO).some((s) => s.kind === "critique_failed")).toBe(false);
  });
  it("when the critique was unavailable, keeps only the last failure before each of this pair's verdicts", () => {
    expect(alertTimeline(rows, HERO, "unavailable").map((s) => s.seq)).toEqual([2, 3, 8, 9]);
  });
  it("filters the trace query to this pair", () => {
    expect(skepticTraceFilter(HERO)).toBe("input_summary.ilike.*CHN-AD-2026-001182|CHN-VL-2026-000877*");
    expect(skepticTraceFilter(HERO, "unavailable")).toMatch(/,action\.eq\.critique_failed$/);
  });
});

describe("capFlipped", () => {
  it("is true when the trace ends on a send-back but the alert was approved at the cap", () => {
    const steps = alertTimeline([ev(1, "send_back", "pair A-1|B-2 round 1", "score=0.7 struck=[] x")], ["B-2", "A-1"]);
    expect(capFlipped(steps, { rounds: 1, struck: [], verdict: "approved" })).toBe(true);
    expect(capFlipped(steps, { rounds: 1, struck: [], verdict: "needs_revision" })).toBe(false);
  });
});

describe("skepticSummary", () => {
  it("says nothing struck when no factor was struck (the hero alert's on-camera line)", () => {
    expect(skepticSummary({ rounds: 2, struck: [], verdict: "approved", model_critique: "applied" } as never))
      .toBe("Reviewed in 2 rounds · verdict: approved · nothing struck · model critique applied");
  });
  it("names struck factors when there are some, and an unavailable critique", () => {
    expect(skepticSummary({ rounds: 1, struck: ["vehicle"], verdict: "needs_revision", model_critique: "unavailable" } as never))
      .toBe("Reviewed in 1 round · verdict: sent back for revision · struck vehicle · model critique unavailable (rule checks only)");
    expect(skepticSummary(null)).toBe("No Skeptic record.");
  });
});

describe("droppedLinks", () => {
  it("lists drop events newest first, once per run and pair, with the reason", () => {
    const rows = [
      ev(50, "drop", "pair CHN-CM-2025-000450|CHN-CM-2025-000461 round 1", "score=0.6937 struck=[] Age bands differ", "rejected", "run_a"),
      ev(51, "drop", "pair CHN-CM-2025-000450|CHN-CM-2025-000461 round 1", "score=0.6937 struck=[] Age bands differ", "rejected", "run_a"),
      ev(52, "approve", "pair X-1|Y-2 round 1", "score=0.8 struck=[] ok", "approved", "run_a"),
    ];
    expect(droppedLinks(rows)).toEqual([{ runId: "run_a", ts: rows[1].ts, pair: ["CHN-CM-2025-000450", "CHN-CM-2025-000461"],
      round: 1, score: 0.6937, reason: "Age bands differ" }]);
  });
});
