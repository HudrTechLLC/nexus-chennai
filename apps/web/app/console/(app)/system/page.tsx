import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { runTone, stateTone, type RunRow, type StatusRow } from "@/lib/trace";
import { droppedLinks, type SkepticEventRow } from "@/lib/skeptic";
import { evalReport } from "@/lib/evalReport.data";
import { EvalSummary } from "@/components/console/system/EvalSummary";

export const dynamic = "force-dynamic";

const TONE = {
  good: "border-signal text-signal",
  warn: "border-accent text-accent",
  bad: "border-red-500 text-red-600",
  muted: "border-line text-muted",
} as const;

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "—";

/** System status (spec G2): adapter and lane health from the worker heartbeat, and recent agent runs. */
export default async function SystemPage() {
  await requireOfficer("admin");
  const sb = consoleServerClient();
  const [status, runs, drops] = await Promise.all([
    sb.from("system_status").select("component, state, detail, checked_at").order("component"),
    sb.from("runs").select("run_id, kind, started, finished, status, log_path").order("started", { ascending: false }).limit(25),
    // WS3-26: links the Skeptic dropped. They never become alerts, so the trace is their only record.
    sb.from("trace_events").select("run_id, seq, ts, action, input_summary, output_summary, status")
      .eq("agent_name", "Skeptic").eq("action", "drop").order("ts", { ascending: false }).limit(100),
  ]);
  const dropped = droppedLinks((drops.data ?? []) as SkepticEventRow[]).slice(0, 30);
  const components = (status.data ?? []) as StatusRow[];
  const recent = (runs.data ?? []) as RunRow[];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">System</h1>
        <p className="text-sm text-muted">
          Health of every service the agents use, as reported by the worker on each pass, and the latest agent runs.
          Open a run to see each step: agent, model and receipt, Zetaris queries, engines and Skeptic decisions.
        </p>
        <Link href="/console/system/sources" className="mt-1 inline-block text-sm text-accent underline-offset-2 hover:underline">
          Data sources: what Zetaris federates →
        </Link>
      </div>

      <EvalSummary report={evalReport} />

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Services</h2>
        {status.error && <p role="alert" className="text-sm text-red-600">Could not load status: {status.error.message}</p>}
        {!status.error && components.length === 0 && (
          <p className="text-sm text-muted">No heartbeat yet. Start the worker (<span className="font-mono text-xs">python -m app.worker</span>).</p>
        )}
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {components.map((c) => (
            <li key={c.component} className="flex items-start justify-between gap-3 rounded-lg border border-line p-3">
              <div className="min-w-0">
                <div className="font-mono text-xs">{c.component}</div>
                <div className="truncate text-xs text-muted" title={JSON.stringify(c.detail ?? {})}>
                  {detailText(c.detail)}
                </div>
                <div className="text-xs text-muted">checked {when(c.checked_at)}</div>
              </div>
              <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${TONE[stateTone(c.state)]}`}>{c.state}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Recent agent runs</h2>
        {runs.error && <p role="alert" className="text-sm text-red-600">Could not load runs: {runs.error.message}</p>}
        {!runs.error && recent.length === 0 && <p className="text-sm text-muted">No runs recorded yet.</p>}
        {recent.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Run</th><th>Kind</th><th>Started</th><th>Finished</th><th>Status</th></tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.run_id} className="border-t border-line">
                  <td className="py-1.5">
                    <Link href={`/console/system/trace/${encodeURIComponent(r.run_id)}`} className="font-mono text-xs underline-offset-2 hover:underline">
                      {r.run_id}
                    </Link>
                  </td>
                  <td>{r.kind}</td>
                  <td className="text-xs">{when(r.started)}</td>
                  <td className="text-xs">{when(r.finished)}</td>
                  <td><span className={`rounded-full border px-2 py-0.5 text-xs ${TONE[runTone(r.status)]}`}>{r.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded-xl border border-line bg-surface p-5" data-testid="dropped-links">
        <h2 className="mb-1 font-semibold">Dropped links</h2>
        <p className="mb-3 text-xs text-muted">
          Pairs the Linker proposed and the Skeptic dropped after re-checking them, with its reason. They never
          became alerts. Newest first, once per run.
        </p>
        {drops.error && <p role="alert" className="text-sm text-red-600">Could not load dropped links: {drops.error.message}</p>}
        {!drops.error && dropped.length === 0 && <p className="text-sm text-muted">The Skeptic has not dropped any link yet.</p>}
        {dropped.length > 0 && (
          <ul className="space-y-3 text-sm">
            {dropped.map((d) => (
              <li key={`${d.runId}:${d.pair.join("|")}`} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                <div className="flex flex-wrap items-baseline gap-x-2 text-xs">
                  {d.pair.map((id, i) => (
                    <span key={id}>
                      {i === 1 && <span className="text-muted">↔ </span>}
                      <Link href={`/console/cases/${encodeURIComponent(id)}`} className="font-mono text-signal hover:underline">{id}</Link>
                    </span>
                  ))}
                  {d.score !== null && <span className="text-muted">score {d.score.toFixed(2)}</span>}
                  {d.round !== null && <span className="text-muted">round {d.round}</span>}
                  <Link href={`/console/system/trace/${encodeURIComponent(d.runId)}`} className="font-mono text-muted hover:underline">{d.runId}</Link>
                  <span className="text-muted">{when(d.ts)}</span>
                </div>
                <p className="mt-0.5 whitespace-pre-wrap break-words">{d.reason}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function detailText(d: Record<string, unknown> | null): string {
  if (!d) return "";
  const parts = Object.entries(d)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  return parts.join(" · ");
}
