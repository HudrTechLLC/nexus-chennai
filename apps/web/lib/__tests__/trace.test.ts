import { describe, expect, it } from "vitest";
import { isRunId, queryRows, querySource, runMode, runTone, stateTone, stepKind, summarise, type TraceRow } from "../trace";

function row(over: Partial<TraceRow>): TraceRow {
  return {
    run_id: "demo-001", seq: 0, ts: "2026-10-26T18:42:11+05:30", agent_name: "Linker", action: "score_pair",
    input_summary: null, output_summary: null, target_agent: null, model: null, routed_model: null, receipt_id: null,
    zetaris_query_ids: [], engine: null, confidence: null, retry_count: 0, status: "ok", ...over,
  };
}

const RUN: TraceRow[] = [
  row({ seq: 0, agent_name: "Scout Intent", action: "route" }),
  row({ seq: 1, agent_name: "Planner", action: "zetaris_query", output_summary: "rows=40 ms=12 via=zetaris",
        zetaris_query_ids: ["q1"] }),
  row({ seq: 2, agent_name: "Planner", action: "model_call", model: "nvidia/nemotron-3-ultra-550b-a55b",
        routed_model: "nvidia/nemotron-3-ultra-550b-a55b", receipt_id: "ns_rcpt_1",
        ts: "2026-10-26T18:42:31+05:30" }),
  row({ seq: 3, agent_name: "Linker", action: "memory_applied", engine: "hmem" }),
  row({ seq: 4, agent_name: "Skeptic", action: "strike_factor", status: "needs_revision", target_agent: "Linker" }),
  row({ seq: 5, agent_name: "Skeptic", action: "send_back", status: "needs_revision", target_agent: "Planner" }),
  row({ seq: 6, agent_name: "Extractor", action: "model_output_invalid", status: "retry", retry_count: 0 }),
  row({ seq: 7, agent_name: "Extractor", action: "vision_unavailable", status: "degraded" }),
  row({ seq: 8, agent_name: "Alert writer", action: "write_alert" }),
  row({ seq: 9, agent_name: "Extractor", action: "model_call", status: "replayed", model: "nvidia/fast",
        receipt_id: "ns_rcpt_1", ts: "2026-10-26T18:43:11+05:30" }),
];

describe("stepKind", () => {
  it("labels the events judges look for", () => {
    expect(RUN.map(stepKind)).toEqual(["step", "zetaris", "model", "engine", "strike", "send_back", "retry",
                                       "fallback", "alert", "fallback"]);
    expect(stepKind(row({ action: "approve" }))).toBe("critique");
    expect(stepKind(row({ action: "rationale_failed", status: "error" }))).toBe("error");
  });
});

describe("queries", () => {
  it("reads row counts and the answering source", () => {
    expect(queryRows(RUN[1])).toBe(40);
    expect(querySource(RUN[1])).toBe("zetaris");
    expect(querySource(row({ action: "zetaris_query", output_summary: "rows=3 ms=1 via=sample" }))).toBe("sample");
    expect(queryRows(RUN[0])).toBeNull();
  });
});

describe("summarise", () => {
  it("counts models, receipts, queries, engines, strikes and time", () => {
    const s = summarise(RUN);
    expect(s.steps).toBe(10);
    expect(s.modelCalls).toBe(2);
    expect(s.replayed).toBe(1);
    expect(s.receipts).toBe(1);
    expect(s.models).toEqual(["nvidia/fast", "nvidia/nemotron-3-ultra-550b-a55b"]);
    expect(s.zetarisQueries).toBe(1);
    expect(s.zetarisRows).toBe(40);
    expect(s.engines).toEqual(["hmem"]);
    expect([s.strikes, s.sendBacks, s.retries, s.alerts]).toEqual([1, 1, 1, 1]);
    expect(s.seconds).toBe(60);
  });
  it("handles an empty run", () => {
    expect(summarise([]).seconds).toBeNull();
  });
});

describe("helpers", () => {
  it("tones states and validates run ids", () => {
    expect(stateTone("live")).toBe("good");
    expect(stateTone("sample")).toBe("warn");
    expect(stateTone("down")).toBe("bad");
    expect(isRunId("run_7c1e")).toBe(true);
    expect(isRunId("demo-001")).toBe(true);
    expect(isRunId("x,y)")).toBe(false);
    expect(isRunId("")).toBe(false);
  });
});

describe("runTone", () => {
  it("interrupted runs are amber, not red like failures", () => {
    expect(runTone("interrupted")).toBe("warn");
    expect(runTone("failed")).toBe("bad");
    expect(runTone("success")).toBe("good");
    expect(runTone("running")).toBe("muted");
  });
});

describe("runMode", () => {
  const rr = (output_summary: string | null) => row({ seq: 0, agent_name: "api", action: "run_received", output_summary });
  it("reads LIVE from sample_mode=False on the run's run_received event", () => {
    expect(runMode([rr("sample_mode=False deadline=300s"), ...RUN])).toBe("live");
  });
  it("reads SAMPLE from sample_mode=True, in any case", () => {
    expect(runMode([rr("sample_mode=True deadline=300s")])).toBe("sample");
    expect(runMode([rr("deadline=300s sample_mode=true")])).toBe("sample");
  });
  it("is null when the run has no run_received event or it does not carry the flag (never assumed)", () => {
    expect(runMode(RUN)).toBeNull();
    expect(runMode([rr("deadline=300s")])).toBeNull();
    expect(runMode([rr(null)])).toBeNull();
    expect(runMode([rr("not_sample_mode=True")])).toBeNull();
    expect(runMode([])).toBeNull();
  });
  it("ignores a sample_mode mention on any other step", () => {
    expect(runMode([row({ action: "model_call", output_summary: "sample_mode=True" })])).toBeNull();
  });
});
