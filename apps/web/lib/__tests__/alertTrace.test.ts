/**
 * Unit tests for "How this alert was made" (lib/alertTrace.ts): which trace steps belong to one alert (rules from
 * nexus-3, checked against live rows), model/receipt attribution from model_call events, the re-explained
 * rationale, friendly model names and the honest vision-lane note.
 */
import { describe, expect, it } from "vitest";
import { alertSteps, failureOutcome, friendlyModel, pairKey, stepsSummary, visionLane, type AlertStep } from "../alertTrace";
import type { TraceRow } from "../trace";

const A = "CHN-AD-2026-001182", V = "CHN-VL-2026-000877", T = "CHN-TI-2026-001134";
const PAIR = `${A}|${V}`;
const ULTRA = "nvidia/nemotron-3-ultra-550b-a55b", LIGHT = "nvidia/nemotron-3.5-lightning-30b-a3b";
const ALERT = { alertId: "LA-2026-E38C6B38B865", crimes: [V, A] }; // crimes are NOT stored sorted

let seq = 0;
const row = (agent: string, action: string, input: string | null, extra: Partial<TraceRow> = {}): TraceRow => ({
  run_id: "run_1", seq: seq++, ts: "2026-10-20T10:00:00Z", agent_name: agent, action, input_summary: input,
  output_summary: null, target_agent: null, model: null, routed_model: null, receipt_id: null, zetaris_query_ids: [],
  engine: null, confidence: null, retry_count: null, status: "ok", ...extra,
});
const call = (agent: string, input: string, receipt: string, routed = ULTRA) =>
  row(agent, "model_call", input, { model: ULTRA, routed_model: routed, receipt_id: receipt, output_summary: "900 ms" });

const rows: TraceRow[] = [
  // case segment for T (not ours)
  row("Extractor", "features_reused", T),
  call("Planner", "lane=reason plan round 1", "r-plan-T"),
  row("Planner", "plan", null, { model: ULTRA }),
  // case segment for V (ours): planner events carry no crime id
  row("Extractor", "features_reused", V),
  call("Planner", "lane=reason plan round 1", "r-plan-V"),
  row("Planner", "plan", "round 1", { model: ULTRA }),
  row("Planner", "zetaris_query", "q_candidates"),
  row("Planner", "zetaris_query", "q_vehicle_trail"),
  row("Planner", "step_failed", "q_dq_flags", { status: "error" }),
  row("Linker", "score_pair", PAIR, { zetaris_query_ids: ["q1", "q2", "q3"] }),
  row("Linker", "score_pair", `${A}|${T}`, { zetaris_query_ids: ["q9"] }), // another pair
  call("Linker", "lane=reason rationale 2 pairs", "r-explain", LIGHT),
  row("Linker", "explain_pair", `${A}|${T}`, { model: ULTRA }),
  row("Linker", "explain_pair", PAIR, { model: ULTRA }),
  call("Skeptic", "lane=reason critique 2 pairs round 1", "r-skeptic"),
  row("Skeptic", "send_back", `pair ${PAIR} round 1`, { status: "needs_revision" }),
  row("Skeptic", "approve", `pair ${PAIR} round 2`, { zetaris_query_ids: ["q4"] }),
  row("Skeptic", "recheck_unavailable", `${PAIR} vehicle`, { status: "degraded" }),
  row("Alert writer", "write_alert", PAIR, { output_summary: "LA-2026-E38C6B38B865 high 0.79" }),
  row("Alert writer", "write_alert", `${A}|${T}`, { output_summary: "LA-2026-OTHER medium 0.61" }),
  // the next case starts: V's segment ends
  row("Extractor", "features_reused", "CHN-XX-2026-000001"),
  row("Planner", "plan", "round 1", { model: ULTRA }),
];

describe("pairKey", () => {
  it("sorts the crime ids itself (link_alerts.crimes is not stored sorted)", () => {
    expect(pairKey([V, A])).toBe(PAIR);
    expect(pairKey([A])).toBeNull();
  });
});

describe("alertSteps", () => {
  const steps = alertSteps(rows, ALERT);
  const by = (action: string, n = 0) => steps.filter((s) => s.action === action)[n];

  it("keeps the alert's case segments and pair events, in run order, and nothing else", () => {
    expect(steps.map((s) => `${s.agent}:${s.action}`)).toEqual([
      "Extractor:features_reused", "Planner:plan", "Planner:step_failed",
      "Linker:score_pair", "Linker:explain_pair", "Skeptic:send_back", "Skeptic:approve", "Skeptic:recheck_unavailable",
      "Alert writer:write_alert",
    ]);
  });
  it("attributes model, routed model and receipt from the nearest preceding model_call of the same agent", () => {
    expect(by("plan")).toMatchObject({ model: "Nemotron 3 Ultra 550B", routedModel: null, receipt: "r-plan-V" });
    expect(by("explain_pair")).toMatchObject({ model: "Nemotron 3 Ultra 550B", routedModel: "Nemotron 3.5 Lightning 30B", receipt: "r-explain" });
    expect(by("send_back")).toMatchObject({ receipt: "r-skeptic", status: "needs_revision" });
    expect(by("send_back").round).toBe("round 1");
    expect(by("approve").round).toBe("round 2");
    expect(by("score_pair").round).toBeNull();
    expect(by("score_pair").receipt).toBeNull();
  });
  it("counts Zetaris queries: the planner's per segment, and the ids on pair events", () => {
    expect(by("plan").zetaris).toBe(2);
    expect(by("score_pair").zetaris).toBe(3);
    expect(by("approve").zetaris).toBe(1);
  });
  it("keeps a timed-out optional Planner step (step_degraded, #334) in the case segment", () => {
    const withDegraded = [...rows.slice(0, 8), row("Planner", "step_degraded", "q_dq_flags", { status: "degraded", seq: rows[7].seq + 0.5 }), ...rows.slice(8)];
    const s = alertSteps(withDegraded, ALERT);
    expect(s.find((x) => x.action === "step_degraded")).toMatchObject({ agent: "Planner", status: "degraded" });
  });
  it("marks an explain with no rationale as a fallback", () => {
    const fb = alertSteps([...rows.slice(0, 13), row("Linker", "explain_pair", PAIR, { output_summary: "(no rationale)" })], ALERT);
    expect(fb.find((s) => s.action === "explain_pair")!.status).toBe("fallback");
  });
  it("adds a later re-explained rationale from its own run, with its model and receipt", () => {
    const rx: TraceRow[] = [
      { ...call("Linker", "lane=reason rationale 2 pairs", "r-rex"), run_id: "reexplain_1" },
      { ...row("Linker", "rationale_reexplained", "LA-2026-E38C6B38B865"), run_id: "reexplain_1" },
      { ...row("Linker", "rationale_reexplained", "LA-2026-OTHER"), run_id: "reexplain_1" },
    ];
    const s = alertSteps(rows, ALERT, rx);
    const last = s[s.length - 1];
    expect(last).toMatchObject({ action: "rationale_reexplained", model: "Nemotron 3 Ultra 550B", receipt: "r-rex", runId: "reexplain_1" });
    expect(s.filter((x) => x.action === "rationale_reexplained")).toHaveLength(1);
  });
  it("is empty when the run has nothing for the alert", () => {
    expect(alertSteps(rows, { alertId: "LA-X", crimes: ["CHN-NO-2026-000001", "CHN-NO-2026-000002"] })).toEqual([]);
  });
});

describe("stepsSummary", () => {
  it("counts steps, model calls (receipts), Zetaris queries and models, and takes the final verdict from the alert", () => {
    const s = stepsSummary(alertSteps(rows, ALERT), "approved");
    expect(s).toEqual({
      steps: 9, modelCalls: 3, zetarisQueries: 6,
      models: ["Nemotron 3 Ultra 550B", "Nemotron 3.5 Lightning 30B"], verdict: "approved",
    });
  });
});

describe("friendlyModel", () => {
  it("names the Nemotron models the way the demo says them", () => {
    expect(friendlyModel(LIGHT)).toBe("Nemotron 3.5 Lightning 30B");
    expect(friendlyModel(ULTRA)).toBe("Nemotron 3 Ultra 550B");
    expect(friendlyModel("nvidia/nemotron-3.5-super-vl-120b-a12b")).toBe("Nemotron 3.5 Super VL");
    expect(friendlyModel("some/other-model")).toBe("some/other-model");
    expect(friendlyModel(null)).toBeNull();
  });
});

describe("visionLane", () => {
  const at = "2026-10-27T00:10:00Z";
  const ev = (over: Partial<TraceRow>): TraceRow => ({
    run_id: "run_v", seq: 1, ts: at, agent_name: "Extractor", action: "model_call", input_summary: "lane=vision vision EV-1",
    output_summary: "1200 ms", target_agent: null, model: "nvidia/nemotron-3.5-super-vl-120b-a12b", routed_model: null,
    receipt_id: "rcpt-v", zetaris_query_ids: [], engine: null, confidence: null, retry_count: null, status: "ok", ...over,
  });
  it("says working, with the model, when the latest vision call succeeded", () => {
    expect(visionLane(ev({}))).toEqual({ state: "working", text: "Vision: Nemotron 3.5 Super VL, working", at });
    expect(visionLane(ev({ routed_model: "nvidia/nemotron-3.5-super-vl-120b-a12b" }))!.state).toBe("working");
  });
  it("says unavailable with the reason when the latest vision event failed", () => {
    const failed = visionLane(ev({ action: "vision_unavailable", status: "degraded", model: null, receipt_id: null,
      input_summary: "EV-1", output_summary: 'Extractor: model call failed for vision EV-1: HTTP 502: {"error":{"message":"request has image attachments but no configured vision-capable model"}}' }))!;
    expect(failed.state).toBe("unavailable");
    expect(failed.text).toBe("Vision (Nemotron 3.5 Super VL): unavailable, request has image attachments but no configured vision-capable model; captions used instead");
    expect(failed.at).toBe(at);
    const cut = visionLane(ev({ action: "vision_unavailable", status: "degraded", receipt_id: null,
      output_summary: 'Extractor: model call failed for vision EV-1: HTTP 502: {"error":{"message":"request has image attachments but no configured…' }))!;
    expect(cut.text).toBe("Vision (Nemotron 3.5 Super VL): unavailable, request has image attachments but no configured; captions used instead");
    expect(visionLane(ev({ status: "error", receipt_id: null, output_summary: "timed out" }))!.text)
      .toBe("Vision (Nemotron 3.5 Super VL): unavailable, timed out; captions used instead");
  });
  it("leaves the heartbeat alone when no vision event was recorded", () => {
    expect(visionLane(null)).toBeNull();
  });
});

describe("failureOutcome", () => {
  const st = (seq: number, agent: string, action: string, status: string | null = "ok"): AlertStep =>
    ({ runId: "run_x", seq, agent, action, model: null, routedModel: null, receipt: null, zetaris: 0, status, round: null });
  // the hero run's shape: plan, failed, link, skeptic, re-plan, failed again, alert writer
  const run = [st(1, "Planner", "plan"), st(2, "Planner", "step_failed", "error"), st(3, "Linker", "score_pair"),
    st(4, "Skeptic", "approve", "approved"), st(5, "Planner", "plan"), st(6, "Planner", "step_failed", "error"), st(7, "Alert writer", "write_alert")];
  it("says retried only when the same agent ran again later", () => {
    expect(failureOutcome(run, 1)).toBe("retried");
    expect(failureOutcome(run, 5)).toBe("recovered");
  });
  it("is fatal when nothing ran after the failure, and null for steps that did not fail", () => {
    expect(failureOutcome(run.slice(0, 2), 1)).toBe("fatal");
    expect(failureOutcome(run, 0)).toBeNull();
    expect(failureOutcome(run, 3)).toBeNull();
  });
});
