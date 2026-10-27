import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import {
  runTone,
  isRunId,
  KIND_LABEL,
  querySource,
  queryRows,
  runMode,
  stepKind,
  traceAccess,
  summarise,
  type RunRow,
  type StepKind,
  type TraceRow,
} from "@/lib/trace";
import { RunModeBadge } from "@/components/console/runs/RunModeBadge";
import { receiptCountLine, receiptLabel, receiptNote } from "@/lib/receipts";

const RUN_TONE = {
  good: "border-signal text-signal",
  warn: "border-accent text-accent",
  bad: "border-red-500 text-red-600",
  muted: "border-line text-muted",
} as const;

export const dynamic = "force-dynamic";

const KIND_TONE: Record<StepKind, string> = {
  model: "border-accent text-accent",
  zetaris: "border-signal text-signal",
  engine: "border-line text-ink",
  strike: "border-red-500 text-red-600",
  send_back: "border-red-500 text-red-600",
  critique: "border-signal text-signal",
  retry: "border-accent text-accent",
  fallback: "border-accent text-accent",
  error: "border-red-500 text-red-600",
  alert: "border-signal text-signal",
  step: "border-line text-muted",
};

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" });

/** One agent run, step by step, exactly as the trace recorded it (D3.12; copied and redacted per D-025). */
export default async function TracePage({ params }: { params: { runId: string } }) {
  // Analysts and supervisors may open case, batch and sweep runs; tip and search runs stay admin-only (traceAccess).
  const officer = await requireOfficer("analyst+");
  const isAdmin = officer.role === "admin";
  const runId = decodeURIComponent(params.runId);
  if (!isRunId(runId)) notFound();
  const sb = consoleServerClient();
  // The run row decides access, so it is read before any trace row.
  const run = await sb.from("runs").select("run_id, kind, started, finished, status, log_path").eq("run_id", runId).maybeSingle();
  const r = run.data as RunRow | null;
  if (traceAccess(officer.role, r) !== "ok") notFound();
  const events = await sb.from("trace_events").select("*").eq("run_id", runId).order("seq").limit(5000);
  const rows = (events.data ?? []) as TraceRow[];
  if (!r && rows.length === 0) notFound();
  const s = summarise(rows);

  return (
    <div className="space-y-5">
      <div>
        {isAdmin
          ? <Link href="/console/system" className="text-sm text-muted hover:text-ink">← System</Link>
          : <Link href="/console/alerts" className="text-sm text-muted hover:text-ink">← Alerts</Link>}
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">Run <span className="font-mono">{runId}</span></h1>
          {rows.length > 0 && <RunModeBadge mode={runMode(rows) ?? "unknown"} />}
        </div>
        <p className="text-sm text-muted">
          {r ? <>{r.kind} · <span className={`rounded-full border px-2 py-0.5 text-xs ${RUN_TONE[runTone(r.status)]}`}>{r.status}</span></> : "run row not found"}
          {isAdmin && r?.log_path ? <> · trace file <span className="font-mono text-xs">{r.log_path}</span></> : null}
          {s.seconds !== null ? ` · ${s.seconds}s` : ""}
        </p>
      </div>

      {/* min-w-0 lets the truncated tile text shrink, so the grid never widens the page on phones */}
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 [&>*]:min-w-0">
        <Stat label="Agents" value={s.agents.length} note={s.agents.join(", ")} />
        <Stat label="Model calls" value={s.modelCalls}
              note={`${receiptCountLine(rows.map((x) => x.receipt_id))}${s.replayed ? ` · ${s.replayed} replayed (sample mode)` : ""} · ${s.models.join(", ") || "none"}`} />
        <Stat label="Zetaris queries" value={s.zetarisQueries} note={`${s.zetarisRows} rows read`} />
        <Stat label="Engines" value={s.engines.length} note={s.engines.join(", ") || "none"} />
        <Stat label="Skeptic strikes" value={s.strikes} note={`${s.sendBacks} sent back to the Planner`} />
        <Stat label="Retries" value={s.retries} note={`${s.fallbacks} fallbacks used`} />
        <Stat label="Errors" value={s.errors} note="model, query or deadline" />
        <Stat label="Alerts written" value={s.alerts} note="after the Skeptic" />
      </section>

      {events.error && <p role="alert" className="text-sm text-red-600">Could not load trace: {events.error.message}</p>}

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Steps</h2>
        <ol className="space-y-2">
          {rows.map((e) => {
            const kind = stepKind(e);
            const n = queryRows(e);
            const via = querySource(e);
            return (
              <li key={e.seq} className="grid gap-x-4 gap-y-1 rounded-lg border border-line p-3 text-sm md:grid-cols-[6rem_10rem_1fr]">
                <div className="font-mono text-xs text-muted">#{e.seq} · {time(e.ts)}</div>
                <div>
                  <div className="font-semibold">{e.agent_name}</div>
                  <span className={`mt-1 inline-block rounded-full border px-2 py-0.5 text-xs ${KIND_TONE[kind]}`}>{KIND_LABEL[kind]}</span>
                </div>
                <div className="min-w-0 space-y-1">
                  <div>
                    <span className="font-mono text-xs">{e.action}</span>
                    {e.target_agent && <span className="text-muted"> → {e.target_agent}</span>}
                    {e.status && <span className="text-muted"> · {e.status}</span>}
                    {typeof e.confidence === "number" && <span className="text-muted"> · {e.confidence.toFixed(2)}</span>}
                    {(e.retry_count ?? 0) > 0 && <span className="text-accent"> · retry {e.retry_count}</span>}
                  </div>
                  {e.input_summary && <div className="break-words text-xs text-muted">in: {e.input_summary}</div>}
                  {e.output_summary && <div className="break-words text-xs">out: {e.output_summary}</div>}
                  <div className="flex flex-wrap gap-x-3 font-mono text-xs text-muted">
                    {e.model && <span>model {e.routed_model && e.routed_model !== e.model ? `${e.model} → ${e.routed_model}` : e.model}</span>}
                    {e.receipt_id && <span>{receiptLabel(e.receipt_id)} {e.receipt_id}{receiptNote(e.receipt_id) && <span className="text-signal"> · {receiptNote(e.receipt_id)}</span>}</span>}
                    {(e.zetaris_query_ids ?? []).map((q) => <span key={q}>query {q}</span>)}
                    {n !== null && <span>{n} rows{via === "sample" ? " (sample twin)" : ""}</span>}
                    {e.engine && <span>engine {e.engine}</span>}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
        {rows.length === 0 && !events.error && (
          <p className="text-sm text-muted">This run has no trace rows in Supabase. Its JSONL is in the API&apos;s logs folder.</p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className="truncate text-xs text-muted" title={note}>{note}</div>
    </div>
  );
}
