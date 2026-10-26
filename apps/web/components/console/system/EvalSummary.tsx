import Link from "next/link";
import { beatsText, deltaPts, NO_REPORT, pctOrDash, type EvalReport } from "@/lib/evalReport";

/** System tab card (LNK-10): agents vs rules-only baseline, linking to the full report (not on that page itself). */
export function EvalSummary({ report, link = true }: { report: EvalReport | null; link?: boolean }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="eval-summary">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="eval-summary" className="font-semibold">Linking quality vs rules-only baseline</h2>
        {link && <Link href="/console/system/eval" className="text-sm text-accent underline-offset-2 hover:underline">Full evaluation →</Link>}
      </div>
      {!report ? (
        <p className="text-sm text-muted">{NO_REPORT}</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Metric label="Precision" agent={report.agent.precision} base={report.baseline.precision} />
            <Metric label="Recall" agent={report.agent.recall} base={report.baseline.recall} />
          </div>
          <p className="mt-2 text-xs text-muted">
            {beatsText("precision", report.beats.precision)} · {beatsText("recall", report.beats.recall)}.
            {" "}Planted synthetic series{report.provenance.casesEvaluated !== null ? `, ${report.provenance.casesEvaluated} cases` : ""}.
          </p>
        </>
      )}
    </section>
  );
}

function Metric({ label, agent, base }: { label: string; agent: number | null; base: number | null }) {
  const d = deltaPts(agent, base);
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-3">
        <span className="font-mono text-2xl tabular-nums">{pctOrDash(agent)}</span>
        <span className="text-sm text-muted">agents</span>
        <span className="font-mono tabular-nums text-muted">{pctOrDash(base)}</span>
        <span className="text-sm text-muted">baseline</span>
      </div>
      {d && <div className="mt-1 font-mono text-xs tabular-nums text-muted">{d}</div>}
    </div>
  );
}
