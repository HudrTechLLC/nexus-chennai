import type { Skeptic } from "@/lib/alerts";
import { capFlipped, KIND_LABEL, skepticSummary, type SkepticStep } from "@/lib/skeptic";

const KIND_TONE: Record<SkepticStep["kind"], string> = {
  approve: "bg-signal-soft text-ink",
  send_back: "bg-accent-soft text-ink",
  drop: "bg-bg text-ink border border-line",
  strike: "bg-accent-soft text-ink",
  unverified: "bg-bg text-muted border border-line",
  critique_failed: "bg-bg text-muted border border-line",
  critique_missing: "bg-bg text-muted border border-line",
};

/** The trace keeps a critique's first few hundred characters; mark a cut-off one with an ellipsis. */
const finished = (t: string) => (/[.!?…)"'\]]$/.test(t) ? t : `${t}…`);

function when(ts: string) {
  return new Date(ts).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
}

/**
 * What the Skeptic did with this link (WS3-26): the verdict from the alert's own record, then its review
 * steps from the run trace (critiques, send-backs with reasons, any struck or unverifiable factor).
 * Read-only. The trace is readable by analysts, supervisors and admins (trace_events RLS).
 */
export function SkepticPanel({ skeptic, steps, traceVisible }: {
  skeptic: (Skeptic & { model_critique?: string }) | null;
  steps: SkepticStep[];
  traceVisible: boolean;
}) {
  const flipped = capFlipped(steps, skeptic);
  return (
    <div className="rounded-xl border border-line bg-surface p-5" data-testid="skeptic-panel">
      <h2 className="text-lg font-bold">Skeptic</h2>
      <p className="mt-1 text-sm">{skepticSummary(skeptic)}</p>
      <p className="mt-1 text-xs text-muted">
        The Skeptic re-runs its own Zetaris queries, critiques each link, and approves it, sends it back for a
        narrower check, or drops it.
      </p>
      {steps.length > 0 && (
        <ol className="mt-3 space-y-2 border-l border-line pl-3 text-sm" data-testid="skeptic-timeline">
          {steps.map((s) => (
            <li key={s.seq}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <span className={`rounded px-1.5 py-0.5 font-medium ${KIND_TONE[s.kind]}`}>
                  {KIND_LABEL[s.kind]}{s.factor ? `: ${s.factor.replaceAll("_", " ")}` : ""}
                </span>
                {s.round !== null && <span className="text-muted">round {s.round}</span>}
                {s.score !== null && <span className="text-muted">score {s.score.toFixed(2)}</span>}
                {s.struck.length > 0 && <span className="text-muted">struck {s.struck.join(", ")}</span>}
                <span className="text-muted">{when(s.ts)}</span>
              </div>
              {s.text && <p className="mt-0.5 whitespace-pre-wrap break-words text-sm">{finished(s.text)}</p>}
            </li>
          ))}
        </ol>
      )}
      {flipped && (
        <p className="mt-2 text-xs text-muted">
          The last review sent this link back, but the revision limit was reached, so the final verdict above stands.
        </p>
      )}
      {steps.length === 0 && skeptic && (
        <p className="mt-2 text-xs text-muted">
          {traceVisible ? "No step-by-step record for this run." : "The step-by-step review is visible to analysts, supervisors and admins."}
        </p>
      )}
    </div>
  );
}

export default SkepticPanel;
