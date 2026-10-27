/**
 * Trace viewer helpers (spec G2 /console/system, D3.12). Pure functions so the pages and the tests share them.
 * Rows come from Supabase `trace_events`: copies of the agents' JSONL trace, redacted (D-025). Nothing here
 * invents or edits an event; it only groups and labels what the run wrote.
 */

export type TraceRow = {
  run_id: string;
  seq: number;
  ts: string;
  agent_name: string;
  action: string;
  input_summary: string | null;
  output_summary: string | null;
  target_agent: string | null;
  model: string | null;
  routed_model: string | null;
  receipt_id: string | null;
  zetaris_query_ids: string[] | null;
  engine: string | null;
  confidence: number | null;
  retry_count: number | null;
  status: string | null;
};

export type RunRow = {
  run_id: string;
  kind: string;
  started: string;
  finished: string | null;
  status: string;
  log_path: string | null;
};

export type StatusRow = {
  component: string;
  state: "live" | "sample" | "degraded" | "down" | "off";
  detail: Record<string, unknown> | null;
  checked_at: string;
};

/** What a step is, for the badge on its timeline row. */
export type StepKind =
  | "model"
  | "zetaris"
  | "engine"
  | "strike"
  | "send_back"
  | "critique"
  | "retry"
  | "fallback"
  | "error"
  | "alert"
  | "step";

const FALLBACK_STATUSES = ["degraded", "fallback", "replayed"];

export function stepKind(r: Pick<TraceRow, "action" | "status" | "retry_count" | "engine" | "model">): StepKind {
  const a = r.action;
  const s = (r.status ?? "").toLowerCase();
  if (s === "error" || a.endsWith("_failed") || a === "deadline_exceeded") return "error";
  if (a === "strike_factor") return "strike";
  if (a === "send_back" || s === "needs_revision") return a === "strike_factor" ? "strike" : "send_back";
  if (a === "model_output_invalid" || (r.retry_count ?? 0) > 0) return "retry";
  if (FALLBACK_STATUSES.includes(s) || a.includes("fallback") || a.startsWith("skip_model")) return "fallback";
  if (a === "approve" || a === "drop" || a.startsWith("critique")) return "critique";
  if (a === "write_alert" || a === "write_hotspot") return "alert";
  if (a === "model_call") return "model";
  if (a === "zetaris_query") return "zetaris";
  if (r.engine) return "engine";
  return "step";
}

export const KIND_LABEL: Record<StepKind, string> = {
  model: "Model",
  zetaris: "Zetaris",
  engine: "Engine",
  strike: "Strike",
  send_back: "Send back",
  critique: "Skeptic",
  retry: "Retry",
  fallback: "Fallback",
  error: "Error",
  alert: "Alert",
  step: "Step",
};

/** Row count reported by a Zetaris query event ("rows=12 ms=40 via=zetaris"). */
export function queryRows(r: Pick<TraceRow, "action" | "output_summary">): number | null {
  if (r.action !== "zetaris_query") return null;
  const m = /rows=(\d+)/.exec(r.output_summary ?? "");
  return m ? Number(m[1]) : null;
}

/** "via=sample" means the DuckDB twin over data/sample answered (sample mode). */
export function querySource(r: Pick<TraceRow, "action" | "output_summary">): "zetaris" | "sample" | null {
  if (r.action !== "zetaris_query") return null;
  const m = /via=(\w+)/.exec(r.output_summary ?? "");
  return m ? (m[1] === "sample" ? "sample" : "zetaris") : null;
}

export type RunSummary = {
  steps: number;
  agents: string[];
  modelCalls: number;
  replayed: number;
  receipts: number;
  models: string[];
  zetarisQueries: number;
  zetarisRows: number;
  engines: string[];
  strikes: number;
  sendBacks: number;
  retries: number;
  fallbacks: number;
  errors: number;
  alerts: number;
  seconds: number | null;
};

function uniq(xs: (string | null | undefined)[]): string[] {
  return Array.from(new Set(xs.filter((x): x is string => !!x))).sort();
}

/** Counts judges look for: who acted, which models (with receipts), which Zetaris queries, which engines. */
export function summarise(rows: TraceRow[]): RunSummary {
  const kinds = rows.map(stepKind);
  const count = (k: StepKind) => kinds.filter((x) => x === k).length;
  const modelRows = rows.filter((r) => r.action === "model_call");
  const queryRowsOnly = rows.filter((r) => r.action === "zetaris_query");
  const times = rows.map((r) => Date.parse(r.ts)).filter((t) => !Number.isNaN(t));
  return {
    steps: rows.length,
    agents: uniq(rows.map((r) => r.agent_name)),
    modelCalls: modelRows.length,
    replayed: modelRows.filter((r) => r.status === "replayed").length,
    receipts: uniq(modelRows.map((r) => r.receipt_id)).length,
    models: uniq(modelRows.map((r) => r.routed_model ?? r.model)),
    zetarisQueries: queryRowsOnly.length,
    zetarisRows: queryRowsOnly.reduce((n, r) => n + (queryRows(r) ?? 0), 0),
    engines: uniq(rows.map((r) => r.engine)),
    strikes: count("strike"),
    sendBacks: count("send_back"),
    retries: count("retry"),
    fallbacks: count("fallback"),
    errors: count("error"),
    alerts: count("alert"),
    seconds: times.length > 1 ? Math.round((Math.max(...times) - Math.min(...times)) / 100) / 10 : null,
  };
}

/** Status pill colour per component state. */
export function stateTone(state: string): "good" | "warn" | "bad" | "muted" {
  if (state === "live") return "good";
  if (state === "sample" || state === "degraded") return "warn";
  if (state === "down") return "bad";
  return "muted";
}

/** Runs may only be looked up by a safe id (it goes into a query filter and a URL). */
export function isRunId(v: string): boolean {
  return /^[A-Za-z0-9_-]{1,80}$/.test(v);
}

/**
 * Pill tone for a run status. "interrupted" (a run stopped mid-way, 0006_04) is amber, not red:
 * it is not a failure of the pipeline.
 */
export function runTone(status: string | null | undefined): "good" | "warn" | "bad" | "muted" {
  switch ((status ?? "").toLowerCase()) {
    case "success": return "good";
    case "running": return "muted";
    case "interrupted": return "warn";
    default: return "bad";
  }
}

/**
 * The run's mode from its own `run_received` event ("sample_mode=True|False", written by the API), never assumed.
 * "live": sample_mode off, so every Zetaris and model call had to be live (no sample fallback possible).
 * "sample": sample_mode on, so the run was allowed to fall back to the bundled sample data.
 * null: the run has no run_received row, or that row does not carry the flag.
 */
export function runMode(rows: Pick<TraceRow, "action" | "output_summary">[]): "live" | "sample" | null {
  const r = rows.find((x) => x.action === "run_received");
  const m = /\bsample_mode=(true|false)\b/i.exec(r?.output_summary ?? "");
  return m ? (m[1].toLowerCase() === "true" ? "sample" : "live") : null;
}
