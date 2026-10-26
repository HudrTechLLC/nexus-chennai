import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { coverageCapLine, coverageOf, decisionState, factorRows, latestDecision, pct, queryIds, REASON_LABEL } from "@/lib/alerts";
import { audit, crimeBriefs, crimeTitle, fetchAlert, officerNames, type CrimeBrief } from "@/lib/alertsData";
import { canDecideAlerts } from "@/lib/roles";
import { BandPill, FactorBars, ScoreRing, StatusPill } from "@/components/console/alerts/AlertBits";
import { DecisionForm } from "@/components/console/alerts/DecisionForm";
import { AlertsLive } from "@/components/console/alerts/AlertsLive";

export const dynamic = "force-dynamic";

function fmt(at: string | null) {
  if (!at) return "—";
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function CrimeColumn({ c, id }: { c: CrimeBrief | undefined; id: string }) {
  return (
    <div className="rounded-lg border border-line p-3 text-sm">
      <h3 className="font-semibold">{crimeTitle(c, id)}</h3>
      <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-y-1">
        <dt className="text-muted">Crime</dt><dd className="font-mono text-xs">{id}</dd>
        <dt className="text-muted">Type</dt><dd>{c ? `${c.category}${c.sub_type ? ` · ${c.sub_type}` : ""}` : "—"}</dd>
        <dt className="text-muted">Station</dt><dd>{c?.station_name ?? "—"}</dd>
        <dt className="text-muted">Occurred</dt><dd>{c?.full ? fmt(c.occurred_from) : c?.week ?? "—"}</dd>
        <dt className="text-muted">Place</dt><dd>{c?.full ? c.address ?? "—" : c?.cell ? `area cell ${c.cell.slice(0, 9)}…` : "—"}</dd>
      </dl>
      {c && c.mo_tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {c.mo_tags.map((t) => <span key={t} className="rounded bg-bg px-1.5 py-0.5 text-xs">{t.replaceAll("_", " ")}</span>)}
        </div>
      )}
      {c && !c.full && (
        <p className="mt-2 text-xs text-muted">Another station&apos;s case: you see the city-wide summary. Full detail is for that station and analysts.</p>
      )}
      {c?.full && <Link href={`/console/cases/${encodeURIComponent(id)}`} className="mt-2 inline-block text-xs text-signal hover:underline">Open case file →</Link>}
    </div>
  );
}

export default async function AlertDetail({ params }: { params: { alertId: string } }) {
  const officer = await requireOfficer("all");
  const sb = consoleServerClient();
  const alertId = decodeURIComponent(params.alertId);
  const alert = await fetchAlert(sb, alertId);
  if (!alert) notFound();
  await audit(sb, "view_alert", "link_alert", alertId);

  const crimes = await crimeBriefs(sb, alert.crimes);
  const decisions = [...(alert.alert_decisions ?? [])].sort((a, b) => b.at.localeCompare(a.at));
  const names = await officerNames(sb, decisions.map((d) => d.by));
  const state = decisionState(alert);
  const rows = factorRows(alert.link_factors);
  const qids = queryIds(alert.link_factors);
  const last = latestDecision(decisions);
  const stationsLabel = alert.crimes.map((id) => crimes[id]?.station_name.replace(/^PS-/, "") ?? id).filter((v, i, a) => a.indexOf(v) === i).join(" and ");

  return (
    <div className="space-y-5">
      <AlertsLive alertId={alertId} />
      <Link href="/console/alerts" className="text-sm text-muted hover:text-ink">← Link alerts</Link>

      <header className="flex flex-wrap items-center gap-5 rounded-xl border border-line bg-surface p-5">
        <ScoreRing score={alert.score} band={alert.band} size={88} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <BandPill band={alert.band} />
            <StatusPill state={state} />
            <span className="font-mono text-xs text-muted">{alert.alert_id} · {alert.kind} · raised {fmt(alert.created_at)}</span>
          </div>
          <h1 className="mt-1 text-2xl font-bold">{alert.crimes.map((id) => crimeTitle(crimes[id], id)).join(" ↔ ")}</h1>
          <p className="mt-1 text-sm">{alert.rationale}</p>
          <p className="mt-1 font-mono text-xs text-muted">
            score {alert.score.toFixed(2)} · coverage {pct(coverageOf(alert))} of factor weight had data
            {alert.run_id && officer.role === "admin" && (
              <> · <Link className="text-signal hover:underline" href={`/console/system/trace/${encodeURIComponent(alert.run_id)}`}>run {alert.run_id}</Link></>
            )}
          </p>
          {coverageCapLine(alert) && <p className="mt-1 text-xs text-muted">{coverageCapLine(alert)}</p>}
        </div>
      </header>

      <section className="grid gap-3 md:grid-cols-2">
        {alert.crimes.map((id) => <CrimeColumn key={id} c={crimes[id]} id={id} />)}
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Factors</h2>
        <p className="text-xs text-muted">Bar = factor value; w = weight; → = contribution to the score. Struck factors were removed by the Skeptic.</p>
        <div className="mt-3"><FactorBars rows={rows} /></div>
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Evidence</h2>
        <table className="mt-2 w-full text-left text-sm">
          <thead className="text-xs uppercase text-muted">
            <tr><th className="py-1">Factor</th><th>Why</th><th>Source row</th><th>Zetaris query</th></tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.factor} className="border-t border-line align-top">
                <td className={`py-2 pr-3 ${f.struck_by_skeptic ? "text-muted line-through" : ""}`}>{f.label}</td>
                <td className="py-2 pr-3">{f.reason}</td>
                <td className="py-2 pr-3 font-mono text-xs">
                  {(f.evidence ?? []).length === 0 ? "—" : f.evidence.map((e, i) => <div key={i}>{e.view} · {e.row}</div>)}
                </td>
                <td className="py-2 font-mono text-xs">
                  {(f.evidence ?? []).map((e, i) => <div key={i}>{e.query ?? "—"}{e.query_id ? ` · ${e.query_id}` : ""}</div>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 font-mono text-xs text-muted">Zetaris query ids: {qids.length ? qids.join(", ") : "none recorded"}</p>
      </section>

      <section className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-surface p-5">
          <h2 className="text-lg font-bold">Skeptic</h2>
          {alert.skeptic ? (
            <p className="mt-1 text-sm">
              {alert.skeptic.rounds} round{alert.skeptic.rounds === 1 ? "" : "s"} · verdict <strong>{alert.skeptic.verdict.replace("_", " ")}</strong>
              {alert.skeptic.struck.length ? <> · struck {alert.skeptic.struck.join(", ")}</> : " · nothing struck"}
            </p>
          ) : <p className="mt-1 text-sm text-muted">No Skeptic record.</p>}
        </div>
        <div className="rounded-xl border border-line bg-surface p-5">
          <h2 className="text-lg font-bold">Memory applied</h2>
          {(alert.memory_applied ?? []).length === 0 ? <p className="mt-1 text-sm text-muted">No earlier decisions changed this score.</p> : (
            <ul className="mt-1 space-y-1 text-sm">
              {alert.memory_applied.map((m) => (
                <li key={m.memory_id}><span className="rounded bg-accent-soft px-1.5 py-0.5 font-mono text-xs">{m.effect}</span> {m.text}</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {alert.recommended_action && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="text-lg font-bold">Recommended action</h2>
          <p className="mt-1 text-sm">{alert.recommended_action}</p>
        </section>
      )}

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Decision</h2>
        {state === "pending" && canDecideAlerts(officer.role) && <div className="mt-2"><DecisionForm alertId={alertId} stationsLabel={stationsLabel} /></div>}
        {state === "pending" && !canDecideAlerts(officer.role) && <p className="mt-1 text-sm text-muted">Waiting for an analyst or supervisor.</p>}
        {state !== "pending" && last && (
          <p className="mt-1 text-sm">
            <strong>{last.decision === "approve" ? "Approved" : `Rejected · ${last.reason_code ? REASON_LABEL[last.reason_code] : ""}`}</strong>{" "}
            by {names[last.by] ?? "an analyst"}, {fmt(last.at)}{last.note ? `: ${last.note}` : ""}
          </p>
        )}
        {decisions.length > 0 && (
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer text-muted">Decision history ({decisions.length})</summary>
            <ul className="mt-2 space-y-1">
              {decisions.map((d) => (
                <li key={d.decision_id}>
                  {fmt(d.at)} · {names[d.by] ?? "officer"} · {d.decision}{d.reason_code ? ` (${REASON_LABEL[d.reason_code]})` : ""}
                  {d.note ? ` · ${d.note}` : ""} · {d.processed_at ? "applied" : "not applied yet"}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </div>
  );
}
