import Link from "next/link";
import { failureOutcome, stepsSummary, type AlertStep } from "@/lib/alertTrace";

const STATUS_TONE: Record<string, string> = {
  approved: "text-signal", needs_revision: "text-accent", rejected: "text-red-600", degraded: "text-accent",
  error: "text-red-600", fallback: "text-accent", retry: "text-accent",
};

const ACTION_LABEL: Record<string, string> = { rationale_reexplained: "rationale re-explained (later run)" };

/** A failed step the run went on from reads amber, not red; red only when nothing ran after it. */
const FAILURE_TONE = { retried: "text-amber-700", recovered: "text-amber-700", fatal: "text-red-600" } as const;
const FAILURE_TITLE = {
  retried: "This step failed and the same agent ran again later in this run.",
  recovered: "This step failed; the run carried on without it.",
  fatal: "This step failed and the run stopped here.",
} as const;

/**
 * "How this alert was made" (WS3-25): each recorded step of the agent run that concerns this alert, with the
 * model asked for, the model Nightshift routed to (when different), the receipt and the Zetaris query count.
 * Collapsed by default (nexus-4): the summary line alone sits above Factors; the steps open on demand.
 */
export function AlertHowMade({ steps, runId, verdict, canOpenTrace }: {
  steps: AlertStep[]; runId: string | null; verdict: string | null; canOpenTrace: boolean;
}) {
  const s = stepsSummary(steps, verdict);
  const line = steps.length === 0
    ? (runId ? "No recorded steps for this alert in its run." : "This alert has no agent run recorded.")
    : [
        `${s.steps} steps`,
        `${s.modelCalls} model ${s.modelCalls === 1 ? "call" : "calls"}`,
        `${s.zetarisQueries} Zetaris ${s.zetarisQueries === 1 ? "query" : "queries"}`,
        ...s.models,
        ...(s.verdict ? [`Skeptic's final verdict: ${s.verdict.replaceAll("_", " ")}`] : []),
      ].join(" · ");
  return (
    <details className="group rounded-xl border border-line bg-surface p-5">
      <summary className="cursor-pointer list-none">
        <span className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-lg font-bold">
            <span aria-hidden className="mr-1 inline-block text-muted transition-transform group-open:rotate-90">▸</span>
            How this alert was made
          </span>
          <span className="text-xs text-muted group-open:hidden">Show steps</span>
        </span>
        <span className="mt-1 block text-sm text-muted">{line}</span>
      </summary>
      {steps.length > 0 && (
        <ol className="mt-3 space-y-1.5 text-sm">
          {steps.map((x, i) => {
            const failed = failureOutcome(steps, i);
            return (
            <li key={`${x.runId}:${x.seq}`} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-t border-line pt-1.5 first:border-t-0 first:pt-0">
              <span className="font-medium">{x.agent}</span>
              <span className="font-mono text-xs text-muted">{ACTION_LABEL[x.action] ?? x.action}{x.round ? ` · ${x.round}` : ""}</span>
              {x.model && (
                <span className="rounded-full border border-accent px-2 py-0.5 text-xs text-accent">
                  {x.model}
                  {x.routedModel && <> → routed to {x.routedModel}</>}
                </span>
              )}
              {!x.model && x.routedModel && (
                <span className="rounded-full border border-accent px-2 py-0.5 text-xs text-accent">{x.routedModel}</span>
              )}
              {x.zetaris > 0 && (
                <span className="rounded-full border border-signal px-2 py-0.5 text-xs text-signal">
                  {x.zetaris} Zetaris {x.zetaris === 1 ? "query" : "queries"}
                </span>
              )}
              {x.receipt && <span className="font-mono text-xs text-muted">receipt {x.receipt}</span>}
              {x.status && !["ok", "success"].includes(x.status) && (
                <span
                  className={`text-xs ${failed ? FAILURE_TONE[failed] : STATUS_TONE[x.status] ?? "text-muted"}`}
                  title={failed ? FAILURE_TITLE[failed] : undefined}
                >
                  {failed === "retried" && <span aria-hidden className="mr-0.5">↻</span>}
                  {x.status.replaceAll("_", " ")}
                </span>
              )}
            </li>
            );
          })}
        </ol>
      )}
      <p className="mt-2 text-xs text-muted">
        From the run&apos;s own trace (trace_events), redacted; nothing here is edited after the run.
        {runId && canOpenTrace && (
          <> <Link href={`/console/system/trace/${encodeURIComponent(runId)}`} className="text-signal hover:underline">Full trace →</Link></>
        )}
      </p>
    </details>
  );
}

export default AlertHowMade;
