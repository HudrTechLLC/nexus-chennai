import Link from "next/link";
import { notFound } from "next/navigation";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { coverageCapLine, coverageOf, decisionState, factorRows, latestDecision, pct, queryIds, REASON_LABEL } from "@/lib/alerts";
import { audit, crimeBriefs, crimeTitle, fetchAlert, officerNames, type CrimeBrief } from "@/lib/alertsData";
import { canDecideAlerts } from "@/lib/roles";
import { canPropose } from "@/lib/taskforces";
import { BandPill, FactorBars, ScoreRing, StatusPill } from "@/components/console/alerts/AlertBits";
import { DecisionForm } from "@/components/console/alerts/DecisionForm";
import { AlertsLive } from "@/components/console/alerts/AlertsLive";
import { AlertMapLoader } from "@/components/console/alerts/AlertMapLoader";
import { describeGap, sceneGap, trailOf, type Scene, type TrailRead } from "@/lib/alertMap";
import { memberLonLat } from "@/lib/series";
import { PublicTipsBlock } from "@/components/console/PublicTipsBlock";
import { SkepticPanel } from "@/components/console/alerts/SkepticPanel";
import { alertTimeline, SKEPTIC_ACTIONS, skepticTraceFilter, type SkepticEventRow } from "@/lib/skeptic";
import { AlertHowMade } from "@/components/console/alerts/AlertHowMade";
import { alertSteps } from "@/lib/alertTrace";
import { allows } from "@/lib/roles";
import type { TraceRow } from "@/lib/trace";
import { Id } from "@/components/ui";
import { sharedTags } from "@/lib/alertTrace";

export const dynamic = "force-dynamic";

function fmt(at: string | null) {
  if (!at) return "—";
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function CrimeColumn({ c, id, shared }: { c: CrimeBrief | undefined; id: string; shared: Set<string> }) {
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
          {c.mo_tags.map((t) => shared.has(t)
            ? <span key={t} title="In both cases" className="rounded bg-signal-soft px-1.5 py-0.5 text-xs font-medium text-signal ring-1 ring-inset ring-[color-mix(in_srgb,var(--signal)_30%,transparent)]">{t.replaceAll("_", " ")}</span>
            : <span key={t} className="rounded bg-bg px-1.5 py-0.5 text-xs text-muted">{t.replaceAll("_", " ")}</span>)}
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
  const shared = sharedTags(alert.crimes.map((id) => crimes[id]?.mo_tags ?? []));
  const last = latestDecision(decisions);
  // Map of both scenes + vehicle trail (G2): exact points only where the officer may read the crime.
  const scenes = alert.crimes.flatMap((id) => {
    const c = crimes[id];
    const ll = c ? memberLonLat(c) : null;
    return c && ll ? [{ id, p: ll.p, exact: ll.exact, at: c.full ? c.occurred_from : null, week: c.week, cell: c.cell ?? null, label: crimeTitle(c, id) } as Scene & { label: string }] : [];
  });
  const gap = scenes.length === 2 ? sceneGap(scenes[0], scenes[1]) : null;
  const { data: nearReads } = await sb.from("map_anpr_reads").select("plate_text").in("crime_id", alert.crimes).limit(50);
  const plates = Array.from(new Set((nearReads ?? []).map((r) => r.plate_text as string)));
  const { data: plateReads } = plates.length
    ? await sb.from("map_anpr_reads").select("read_id, camera_id, read_at, plate_text, crime_id, lat, lon").in("plate_text", plates).order("read_at").limit(200)
    : { data: [] };
  const trail = trailOf(
    ((plateReads ?? []) as { read_id: string; camera_id: string; read_at: string; plate_text: string; crime_id: string | null; lat: number; lon: number }[])
      .map((r): TrailRead => ({ read_id: r.read_id, camera_id: r.camera_id, read_at: r.read_at, plate_text: r.plate_text, crime_id: r.crime_id, p: [r.lon, r.lat] })),
    alert.crimes,
  );
  // WS3-26: the Skeptic's steps for this pair, from the run trace (RLS: analyst, supervisor, admin).
  // Filtered to this pair in the query: a batch run has hundreds of Skeptic events.
  const traceVisible = officer.role !== "station_officer";
  const critique = (alert.skeptic as { model_critique?: string } | null)?.model_critique;
  const { data: skepticRows } = alert.run_id && traceVisible
    ? await sb.from("trace_events").select("run_id, seq, ts, action, input_summary, output_summary, status")
        .eq("run_id", alert.run_id).eq("agent_name", "Skeptic").in("action", [...SKEPTIC_ACTIONS])
        .or(skepticTraceFilter(alert.crimes, critique)).order("seq").limit(500)
    : { data: [] };
  const skepticSteps = alertTimeline((skepticRows ?? []) as SkepticEventRow[], alert.crimes, critique);
  const anyStruck = rows.some((f) => f.struck_by_skeptic);
  // How this alert was made (WS3-25): its run's steps, analyst+ only (trace_events RLS).
  const canSeeTrace = allows(officer.role, "analyst+");
  // Its run's steps and any later re-explanation run, fetched together (nexus-4).
  const [traceRes, rexRunRes] = canSeeTrace
    ? await Promise.all([
        alert.run_id
          ? sb.from("trace_events").select("run_id, seq, ts, agent_name, action, input_summary, output_summary, target_agent, model, routed_model, receipt_id, zetaris_query_ids, engine, confidence, retry_count, status").eq("run_id", alert.run_id).order("seq").limit(5000)
          : Promise.resolve({ data: [] }),
        sb.from("trace_events").select("run_id").eq("action", "rationale_reexplained").eq("input_summary", alert.alert_id).limit(10),
      ])
    : [{ data: [] }, { data: [] }];
  const traceRows = (traceRes.data ?? []) as TraceRow[];
  const rexRuns = Array.from(new Set(((rexRunRes.data ?? []) as { run_id: string }[]).map((r) => r.run_id)));
  const rexRows = rexRuns.length
    ? (((await sb.from("trace_events").select("run_id, seq, ts, agent_name, action, input_summary, output_summary, target_agent, model, routed_model, receipt_id, zetaris_query_ids, engine, confidence, retry_count, status")
        .in("run_id", rexRuns).in("action", ["model_call", "rationale_reexplained"]).order("seq").limit(2000)).data ?? []) as TraceRow[])
    : [];
  const howSteps = alertSteps(traceRows, { alertId: alert.alert_id, crimes: alert.crimes }, rexRows);
  const finalVerdict = (alert.skeptic as { verdict?: string } | null)?.verdict ?? null;
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
        {alert.crimes.map((id) => <CrimeColumn key={id} c={crimes[id]} id={id} shared={shared} />)}
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Scenes and vehicle trail</h2>
        <p className="mb-3 text-sm text-muted">
          {gap ? `The two scenes are ${describeGap(gap)}.` : "Only one scene can be placed, so there is no distance to show."}
          {trail.length > 0
            ? ` ANPR cameras read ${trail.map((t) => t.plate).join(", ")} near ${trail.length === 1 ? "a scene" : "the scenes"}; the gold line joins every read of that plate in time order.`
            : " No ANPR camera read a plate near either scene."}
        </p>
        <AlertMapLoader scenes={scenes} trail={trail} />
        {trail.length > 0 && (
          <ol className="mt-3 space-y-1 text-xs">
            {trail.flatMap((t) => t.reads).map((r) => (
              <li key={r.read_id}>
                <span className="font-mono">{r.plate_text}</span> · camera <span className="font-mono">{r.camera_id}</span> · {fmt(r.read_at)}
                {r.crime_id && alert.crimes.includes(r.crime_id) && <span className="text-muted"> · near {crimeTitle(crimes[r.crime_id], r.crime_id)}</span>}
              </li>
            ))}
          </ol>
        )}
        <p className="mt-2 text-xs text-muted">A camera read is a sighting, not proof of involvement. Sources: crimes (your access), crimes_citywide, map_anpr_reads.</p>
      </section>

      {canSeeTrace && <AlertHowMade steps={howSteps} runId={alert.run_id} verdict={finalVerdict} canOpenTrace={officer.role === "admin"} />}

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Factors</h2>
        <p className="text-xs text-muted">Bar = factor value; w = weight; → = contribution to the score.{anyStruck ? " Struck-through factors were struck by the Skeptic and count for nothing." : ""}</p>
        <div className="mt-3"><FactorBars rows={rows} /></div>
      </section>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="text-lg font-bold">Evidence</h2>
        <div className="-mx-5 overflow-x-auto px-5">
        <table className="mt-2 w-full min-w-[34rem] text-left text-sm">
          <thead className="text-xs uppercase text-muted">
            <tr><th className="py-1">Factor</th><th>Why</th><th>Source row</th><th>Zetaris query</th></tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.factor} className="border-t border-line align-top">
                <td className={`py-2 pr-3 ${f.struck_by_skeptic ? "text-muted line-through" : ""}`}>{f.label}</td>
                <td className="py-2 pr-3">{f.reason}</td>
                <td className="py-2 pr-3 font-mono text-xs">
                  {(f.evidence ?? []).length === 0 ? "—" : f.evidence.map((e, i) => <div key={i} className="whitespace-nowrap">{e.view} · <Id value={String(e.row)} max={22} tone="ink" /></div>)}
                </td>
                <td className="py-2 font-mono text-xs">
                  {(f.evidence ?? []).map((e, i) => <div key={i} className="whitespace-nowrap">{e.query ?? "—"}{e.query_id ? <> · <Id value={e.query_id} tone="evidence" /></> : ""}</div>)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        <p className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-muted">Zetaris query ids: {qids.length ? qids.map((q, i) => <span key={q}><Id value={q} tone="evidence" />{i < qids.length - 1 ? "," : ""}</span>) : "none recorded"}</p>
      </section>

      {/* items-start: Memory applied keeps its own height beside a taller Skeptic timeline */}
      <section className="grid gap-3 md:grid-cols-2 md:items-start">
        <SkepticPanel skeptic={alert.skeptic} steps={skepticSteps} traceVisible={traceVisible} />
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

      <PublicTipsBlock crimeIds={alert.crimes} label={(id) => crimeTitle(crimes[id], id)} />

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
        {alert.status === "approved" && canPropose(officer.role) && (
          <p className="mt-3">
            <Link href={`/console/taskforces/new?alert_id=${encodeURIComponent(alertId)}`}
              className="inline-block rounded-md bg-ink px-3 py-1.5 text-sm font-semibold text-bg hover:opacity-90">
              Propose joint task force
            </Link>
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
