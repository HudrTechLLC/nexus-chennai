/**
 * "How this alert was made" (WS3-25): the steps of the alert's agent run that concern this alert, read from
 * `trace_events` as the run wrote them. Pure helpers: they filter and label, they never invent a step.
 *
 * Which events belong to an alert (nexus-3, checked against live rows):
 *  - pair events: input_summary is the pair key "<A>|<B>" (sorted), or starts "pair <A>|<B> " or "<A>|<B> ";
 *    write_alert also needs output_summary to start with the alert id;
 *  - case events: an Extractor event whose input is one of the alert's crimes starts that crime's case segment,
 *    which runs until the next Extractor case event; Planner plan/route/step_failed/step_degraded events in it
 *    belong to it;
 *  - model + receipt: only `model_call` events carry receipt_id, once per CALL (one call can cover two pairs);
 *    a step takes the nearest preceding model_call by the same agent.
 */
import type { TraceRow } from "@/lib/trace";

/** Friendly names for the models the demo talks about; anything else is shown as its id. */
const MODEL_NAMES: [RegExp, string][] = [
  [/nemotron-3\.5-lightning-30b/i, "Nemotron 3.5 Lightning 30B"],
  [/nemotron-3-ultra-550b/i, "Nemotron 3 Ultra 550B"],
  [/nemotron-3\.5-super-vl/i, "Nemotron 3.5 Super VL"],
];

export function friendlyModel(id: string | null | undefined): string | null {
  if (!id) return null;
  return MODEL_NAMES.find(([re]) => re.test(id))?.[1] ?? id;
}

/** The Linker's pair key: the two crime ids sorted, joined by "|" (null unless the alert links two crimes). */
export function pairKey(crimes: string[]): string | null {
  return crimes.length === 2 ? [...crimes].sort().join("|") : null;
}

export type AlertStep = {
  runId: string;
  seq: number;
  agent: string;
  action: string;
  /** Model asked for (friendly name). */
  model: string | null;
  /** Model Nightshift actually routed to, only when it differs. */
  routedModel: string | null;
  receipt: string | null;
  zetaris: number;
  status: string | null;
  /** "round 2" when the step was a re-plan or a later Skeptic round. */
  round: string | null;
};

const CRIME_ID = /^CHN-[A-Z]{2}-\d{4}-\d{6}$/;
// step_degraded: a timed-out optional Planner step (#334), e.g. q_dq_flags on every live case run
const PLANNER_STEPS = new Set(["plan", "route", "step_failed", "step_degraded"]);
const MODEL_STEPS = new Set(["explain_pair", "plan", "approve", "send_back", "drop", "strike_factor", "critique_missing", "rationale_reexplained"]);

function toStep(r: TraceRow, call: TraceRow | null, zetaris: number): AlertStep {
  const useCall = call && MODEL_STEPS.has(r.action);
  const model = friendlyModel(useCall ? call.model : r.model);
  const routed = friendlyModel(useCall ? call.routed_model : r.routed_model);
  const noRationale = r.action === "explain_pair" && /^\(no rationale\)/.test(r.output_summary ?? "");
  return {
    runId: r.run_id,
    seq: r.seq,
    agent: r.agent_name,
    action: r.action,
    model,
    routedModel: routed && routed !== model ? routed : null,
    receipt: useCall ? call.receipt_id : r.receipt_id,
    zetaris,
    status: noRationale ? "fallback" : r.status,
    round: /\bround \d+\b/.exec(r.input_summary ?? "")?.[0] ?? null,
  };
}

/** Steps of the alert's run that belong to it, then any later re-explanation of its rationale (`reexplain`). */
export function alertSteps(rows: TraceRow[], alert: { alertId: string; crimes: string[] }, reexplain: TraceRow[] = []): AlertStep[] {
  const pair = pairKey(alert.crimes);
  const crimes = new Set(alert.crimes);
  const isPairEvent = (r: TraceRow) => {
    if (!pair) return false;
    const input = r.input_summary ?? "";
    const hit = input === pair || input.startsWith(`pair ${pair} `) || input.startsWith(`${pair} `);
    if (!hit) return false;
    return r.action === "write_alert" ? (r.output_summary ?? "").startsWith(alert.alertId) : true;
  };

  const out: AlertStep[] = [];
  const lastCall = new Map<string, TraceRow>();
  let inCase = false;
  let planStep: AlertStep | null = null;
  for (const r of [...rows].sort((a, b) => a.seq - b.seq)) {
    if (r.action === "model_call") {
      lastCall.set(r.agent_name, r);
      continue;
    }
    if (r.agent_name === "Extractor" && CRIME_ID.test(r.input_summary ?? "")) {
      inCase = crimes.has(r.input_summary!);
      planStep = null;
      if (inCase) out.push(toStep(r, null, r.zetaris_query_ids?.length ?? 0));
      continue;
    }
    if (inCase && r.agent_name === "Planner") {
      if (r.action === "zetaris_query") {
        if (planStep) planStep.zetaris += 1;
        continue;
      }
      if (PLANNER_STEPS.has(r.action)) {
        const s = toStep(r, lastCall.get("Planner") ?? null, r.zetaris_query_ids?.length ?? 0);
        out.push(s);
        if (r.action === "plan") planStep = s;
        continue;
      }
    }
    if (isPairEvent(r)) out.push(toStep(r, lastCall.get(r.agent_name) ?? null, r.zetaris_query_ids?.length ?? 0));
  }

  // A later model-only run may re-explain the rationale (scores untouched): show it after the scoring run.
  const rxCall = new Map<string, TraceRow>();
  for (const r of [...reexplain].sort((a, b) => (a.run_id === b.run_id ? a.seq - b.seq : a.run_id.localeCompare(b.run_id)))) {
    if (r.action === "model_call") rxCall.set(`${r.run_id}:${r.agent_name}`, r);
    else if (r.action === "rationale_reexplained" && r.input_summary === alert.alertId) {
      out.push(toStep(r, rxCall.get(`${r.run_id}:${r.agent_name}`) ?? null, 0));
    }
  }
  return out;
}

export function stepsSummary(steps: AlertStep[], verdict: string | null = null): {
  steps: number; modelCalls: number; zetarisQueries: number; models: string[]; verdict: string | null;
} {
  const models = new Set<string>();
  for (const s of steps) {
    if (s.model) models.add(s.model);
    if (s.routedModel) models.add(s.routedModel);
  }
  return {
    steps: steps.length,
    modelCalls: new Set(steps.map((s) => s.receipt).filter(Boolean)).size,
    zetarisQueries: steps.reduce((n, s) => n + s.zetaris, 0),
    models: Array.from(models).sort(),
    verdict,
  };
}

/** Short reason from a failed vision event: the provider's message if there is one, else the summary. */
function visionReason(summary: string | null): string {
  const text = summary ?? "";
  // the stored summary may be cut mid-string ("…"), so the closing quote is optional
  const msg = /"message"\s*:\s*"([^"]+)/.exec(text)?.[1]?.replace(/…$/, "");
  const plain = text.replace(/^Extractor: model call failed for vision \S+:\s*/, "").replace(/^HTTP \d+:\s*/, "");
  return (msg ?? plain).trim().slice(0, 140) || "no reason recorded";
}

/**
 * The vision lane from data (chief): the latest vision-lane trace event decides. A model_call on lane=vision that
 * succeeded (receipt, no error) means working; a failed call or vision_unavailable / vision_failed means
 * unavailable, with the reason. No event at all: null, and the page keeps the heartbeat as it is.
 */
export function visionLane(latest: TraceRow | null): { state: "working" | "unavailable"; text: string; at: string } | null {
  if (!latest) return null;
  const ok = latest.action === "model_call" && !!latest.receipt_id && latest.status !== "error";
  const model = friendlyModel(latest.routed_model ?? latest.model) ?? "Nemotron 3.5 Super VL";
  return ok
    ? { state: "working", text: `Vision: ${model}, working`, at: latest.ts }
    : {
        state: "unavailable",
        text: `Vision (Nemotron 3.5 Super VL): unavailable, ${visionReason(latest.output_summary)}; captions used instead`,
        at: latest.ts,
      };
}

/**
 * How serious a failed step looks, from what the run did next (never guessed):
 * "recovered" = the run carried on with later steps; "fatal" = nothing ran after it. Steps that did not fail
 * return null. There is deliberately no "retried": the trace records a later step by the same agent, not that
 * it re-ran the failed one (on the hero, a failed query was skipped and the Planner went on with others).
 */
export function failureOutcome(steps: AlertStep[], i: number): "recovered" | "fatal" | null {
  const x = steps[i];
  if (!x || !(x.status === "error" || x.action === "step_failed")) return null;
  const later = steps.slice(i + 1).filter((y) => y.runId === x.runId);
  return later.length ? "recovered" : "fatal";
}

/** MO tags present in every one of the linked crimes (two cards on a pair alert); empty when fewer than two have tags. */
export function sharedTags(tagLists: string[][]): Set<string> {
  const lists = tagLists.filter((l) => l.length > 0);
  if (lists.length < 2) return new Set();
  return new Set(lists[0].filter((t) => lists.every((l) => l.includes(t))));
}
