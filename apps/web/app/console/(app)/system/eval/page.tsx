import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { evalReport } from "@/lib/evalReport.data";
import { beatsText, deltaPts, NO_REPORT, pctOrDash, type PairMetrics } from "@/lib/evalReport";
import { EvalSummary } from "@/components/console/system/EvalSummary";

export const dynamic = "force-dynamic";

const n = (v: number | null) => (v === null ? "—" : String(v));

/**
 * Precision / recall vs the rules-only baseline (spec LNK-10, F3; screens /console/system/eval).
 * A static read of the committed report from `python -m app.eval`; nothing is computed here.
 */
export default async function EvalPage() {
  await requireOfficer("admin");
  const r = evalReport;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/console/system" className="text-sm text-muted hover:text-ink">← System</Link>
        <h1 className="mt-1 text-2xl font-bold">Linking evaluation</h1>
        <p className="text-sm text-muted">
          How well the agents find the planted crime series in the synthetic city, against a simple rules-only baseline.
          Scores are computed in code; models only explain (R7). Produced offline by <span className="font-mono text-xs">python -m app.eval</span>.
        </p>
      </div>

      {!r ? (
        <section className="rounded-xl border border-line bg-surface p-5"><p className="text-sm text-muted">{NO_REPORT}</p></section>
      ) : (
        <>
          <EvalSummary report={r} />

          <section className="rounded-xl border border-line bg-surface p-5">
            <h2 className="mb-3 font-semibold">Agents vs baseline, pair level</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr><th className="py-1">Method</th><th>Precision</th><th>Recall</th><th>F1</th><th>TP</th><th>FP</th><th>FN</th><th>Alerts</th><th>False alerts / 100 cases</th></tr>
                </thead>
                <tbody className="font-mono tabular-nums">
                  <Row label="Agents (scoring + Skeptic)" m={r.agent} />
                  <Row label="Rules-only baseline" m={r.baseline} />
                  <tr className="border-t border-line text-xs text-muted">
                    <td className="py-1.5 font-sans">Difference</td>
                    <td>{deltaPts(r.agent.precision, r.baseline.precision) ?? "—"}</td>
                    <td>{deltaPts(r.agent.recall, r.baseline.recall) ?? "—"}</td>
                    <td>{deltaPts(r.agent.f1, r.baseline.f1) ?? "—"}</td>
                    <td colSpan={5} />
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">
              {beatsText("precision", r.beats.precision)} · {beatsText("recall", r.beats.recall)}.
              {r.baseline.rule && <> Baseline rule: <span className="font-mono">{r.baseline.rule}</span>.</>}
              {r.agent.skeptic_strikes !== null && <> Skeptic struck factors on {r.agent.skeptic_strikes} alert{r.agent.skeptic_strikes === 1 ? "" : "s"}.</>}
            </p>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <section className="rounded-xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">By confidence band</h2>
              {r.bands.length === 0 ? <p className="text-sm text-muted">No band breakdown in this report.</p> : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted"><tr><th className="py-1">Band</th><th>Alerts</th><th>Precision</th><th>TP</th><th>FP</th></tr></thead>
                  <tbody className="font-mono tabular-nums">
                    {r.bands.map((b) => (
                      <tr key={b.band} className="border-t border-line">
                        <td className="py-1.5 font-sans capitalize">{b.band}</td><td>{b.alerts}</td><td>{pctOrDash(b.precision)}</td><td>{b.tp}</td><td>{b.fp}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {Object.values(r.bandText).length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-muted">{Object.entries(r.bandText).map(([k, t]) => <li key={k}>{t}</li>)}</ul>
              )}
            </section>

            <section className="rounded-xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-semibold">MO-similarity mode</h2>
              {r.modes.length === 0 ? (
                <p className="text-sm text-muted">
                  One mode in this report{r.moCosine ? <> (<span className="font-mono">mo_cosine {r.moCosine}</span>)</> : null}.
                  A per-mode comparison needs <span className="font-mono text-xs">--mo-cosine both</span>.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted"><tr><th className="py-1">mo_cosine</th><th>Precision</th><th>Recall</th><th>TP</th><th>FP</th><th>FN</th><th>Alerts</th></tr></thead>
                  <tbody className="font-mono tabular-nums">
                    {r.modes.map((m) => (
                      <tr key={m.mode} className="border-t border-line">
                        <td className="py-1.5">{m.mode}{m.mode === r.moCosine ? " (headline)" : ""}</td>
                        <td>{pctOrDash(m.precision)}</td><td>{pctOrDash(m.recall)}</td><td>{n(m.tp)}</td><td>{n(m.fp)}</td><td>{n(m.fn)}</td><td>{n(m.alerts)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {r.tfidfTable && (
                <p className="mt-2 break-words text-xs text-muted">
                  TF-IDF table: {Object.entries(r.tfidfTable).map(([k, v]) => `${k} ${v}`).join(" · ")}
                </p>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-line bg-surface p-5">
            <h2 className="mb-3 font-semibold">By crime type (agents)</h2>
            {r.types.length === 0 ? <p className="text-sm text-muted">No per-type breakdown in this report.</p> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted"><tr><th className="py-1">Type</th><th>Precision</th><th>Recall</th><th>F1</th><th>TP</th><th>FP</th><th>FN</th></tr></thead>
                  <tbody className="font-mono tabular-nums">
                    {r.types.map((t) => (
                      <tr key={t.type} className="border-t border-line">
                        <td className="py-1.5 font-sans">{t.type.replaceAll("_", " ")}</td>
                        <td>{pctOrDash(t.precision)}</td><td>{pctOrDash(t.recall)}</td><td>{pctOrDash(t.f1)}</td><td>{t.tp}</td><td>{t.fp}</td><td>{t.fn}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-line bg-surface p-5">
            <h2 className="mb-3 font-semibold">Series, duplicates and timing</h2>
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div><dt className="text-muted">Series found (purity)</dt><dd className="font-mono tabular-nums">
                {r.agent.series ? `${n(r.agent.series.predicted_series)} (${pctOrDash(r.agent.series.mean_purity)})` : "—"}</dd></div>
              <div><dt className="text-muted">Planted duplicate FIRs flagged</dt><dd className="font-mono tabular-nums">
                {r.duplicates ? `agents ${r.duplicates.flagged_by_agent} · baseline ${r.duplicates.flagged_by_baseline} of ${r.duplicates.truth_pairs}` : "—"}</dd></div>
              <div><dt className="text-muted">Median time per case</dt><dd className="font-mono tabular-nums">
                {r.medianSecondsPerCase === null ? "—" : `${r.medianSecondsPerCase} s`}</dd></div>
            </dl>
          </section>

          <section className="rounded-xl border border-line bg-surface p-5">
            <h2 className="mb-3 font-semibold">Provenance</h2>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <Prov k="Data" v={r.provenance.synthetic === false ? "not marked synthetic" : "synthetic (planted ground truth)"} />
              <Prov k="Sample mode" v={r.provenance.sampleMode === null ? "—" : r.provenance.sampleMode ? "yes (bundled data, no services)" : "no (live Zetaris)"} />
              <Prov k="H-MEM" v={r.provenance.hmem ?? "—"} />
              <Prov k="Scoring weights" v={r.provenance.weightsVersion ?? "—"} mono />
              <Prov k="Cases evaluated" v={n(r.provenance.casesEvaluated)} mono />
              <Prov k="True linked pairs" v={n(r.provenance.truthPositivePairs)} mono />
              <Prov k="Cases with live-model features" v={n(r.provenance.withLiveModelFeatures)} mono />
              <Prov k="Excluded (console-filed, not generated)" v={String(r.provenance.excludedNonGenerated)} mono />
              <Prov k="Run" v={r.provenance.runId ?? "—"} mono />
              <Prov k="Trace" v={r.provenance.logFile ?? "—"} mono />
              {r.provenance.truthDir && <Prov k="Ground truth" v={r.provenance.truthDir} mono />}
            </dl>
            {r.extraProvenance.length > 0 && (
              <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                {r.extraProvenance.map(([k, v]) => <Prov key={k} k={k.replaceAll("_", " ")} v={v} mono />)}
              </dl>
            )}
            {r.provenance.method && <p className="mt-3 text-xs text-muted">Method: {r.provenance.method}</p>}
            {(r.provenance.withoutFeatures.length > 0 || r.provenance.featuresWithoutReceipt.length > 0) && (
              <details className="mt-3 text-xs">
                <summary className="cursor-pointer text-muted">
                  Feature gaps: {r.provenance.withoutFeatures.length} case(s) without features, {r.provenance.featuresWithoutReceipt.length} without a model receipt
                </summary>
                <p className="mt-2 break-words font-mono">{[...r.provenance.withoutFeatures, ...r.provenance.featuresWithoutReceipt].join(", ")}</p>
              </details>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Row({ label, m }: { label: string; m: PairMetrics }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1.5 font-sans">{label}</td>
      <td>{pctOrDash(m.precision)}</td><td>{pctOrDash(m.recall)}</td><td>{pctOrDash(m.f1)}</td>
      <td>{m.tp}</td><td>{m.fp}</td><td>{m.fn}</td><td>{m.alerts}</td><td>{n(m.false_alerts_per_100_cases)}</td>
    </tr>
  );
}

function Prov({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex flex-wrap justify-between gap-2 border-b border-line py-1">
      <dt className="text-muted">{k}</dt>
      <dd className={mono ? "font-mono text-xs" : ""}>{v}</dd>
    </div>
  );
}
