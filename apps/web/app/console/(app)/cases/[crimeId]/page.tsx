import Link from "next/link";
import { notFound } from "next/navigation";
import { Fragment, type ReactNode } from "react";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { decisionState, pct } from "@/lib/alerts";
import { audit, crimeBriefs, crimeTitle, stationNames } from "@/lib/alertsData";
import { buildTimeline, canWriteCase, describe, humanise, maskPii, moRows, type TimelineItem } from "@/lib/cases";
import { fetchCaseFile, fetchCitywide, type CaseFile } from "@/lib/casesData";
import { BandPill, ScoreRing, StatusPill } from "@/components/console/alerts/AlertBits";
import { AppealButton } from "../_components/AppealButton";

export const dynamic = "force-dynamic";

function fmt(at: string | null | undefined) {
  if (!at) return "—";
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Card({ title, count, children, id }: { title: string; count?: number; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="rounded-xl border border-line bg-surface p-5">
      <h2 className="text-lg font-semibold">
        {title}
        {count !== undefined && <span className="ml-2 font-mono text-xs text-muted">{count}</span>}
      </h2>
      <div className="mt-3 text-sm">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-muted">{children}</p>;
}

/** Spec G2 /console/cases/[crimeId]: own station and analysts see everything; others see the city-wide summary. */
export default async function CaseFilePage({ params }: { params: { crimeId: string } }) {
  const officer = await requireOfficer("all");
  const sb = consoleServerClient();
  const crimeId = decodeURIComponent(params.crimeId);
  const file = await fetchCaseFile(sb, crimeId);

  if (!file) {
    const summary = await fetchCitywide(sb, crimeId);
    if (!summary) notFound();
    await audit(sb, "view_case_summary", "crime", crimeId);
    const names = await stationNames(sb, [summary.station_id]);
    return (
      <div className="space-y-4">
        <Link href="/console/cases" className="text-sm text-muted hover:text-ink">← Cases</Link>
        <section className="rounded-xl border border-line bg-surface p-5">
          <p className="font-mono text-xs text-muted">{crimeId}</p>
          <h1 className="mt-1 text-2xl font-bold">{humanise(summary.category)}{summary.sub_type ? ` · ${humanise(summary.sub_type)}` : ""}</h1>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
            <dt className="text-muted">Station</dt><dd>{names[summary.station_id] ?? summary.station_id}</dd>
            <dt className="text-muted">Week</dt><dd>{summary.week ?? "—"}</dd>
            <dt className="text-muted">Area cell</dt><dd className="font-mono text-xs">{summary.cell ?? "—"}</dd>
          </dl>
          {(summary.mo_tags ?? []).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">{(summary.mo_tags ?? []).map((t) => <span key={t} className="rounded bg-bg px-1.5 py-0.5 text-xs">{humanise(t)}</span>)}</div>
          )}
          <p className="mt-4 text-sm text-muted">
            This case belongs to another station, so you see the city-wide summary. The full file is for that station and for analysts.
            Linked alerts that involve your station show both sides in <Link href="/console/alerts?tab=mine" className="text-signal hover:underline">your alerts</Link>.
          </p>
        </section>
      </div>
    );
  }

  await audit(sb, "view_case", "crime", crimeId);
  return <FullCase file={file} canWrite={canWriteCase(officer.role, officer.stationId, file.crime.station_id)} />;
}

async function FullCase({ file, canWrite }: { file: CaseFile; canWrite: boolean }) {
  const sb = consoleServerClient();
  const { crime, features } = file;
  const otherIds = file.alerts.flatMap((a) => a.crimes).filter((id) => id !== crime.crime_id);
  const [names, briefs] = await Promise.all([stationNames(sb, [crime.station_id]), crimeBriefs(sb, otherIds)]);
  const station = names[crime.station_id] ?? crime.station_id;

  const timeline = buildTimeline([
    { at: crime.occurred_from, kind: "occurred", label: `Occurred${crime.address ? ` at ${crime.address}` : ""}` },
    { at: crime.reported_at, kind: "fir", label: `FIR ${crime.fir_no} registered at ${station}` },
    ...file.statements.map((s): TimelineItem => ({ at: s.recorded_at, kind: "statement", label: `Statement from ${s.witness_ref}` })),
    ...file.evidence.map((e): TimelineItem => ({ at: e.captured_at ?? e.created_at, kind: "evidence", label: `${humanise(e.kind)}${e.camera_id ? ` · camera ${e.camera_id}` : ""}` })),
    ...file.diary.map((d): TimelineItem => ({ at: d.at, kind: "diary", label: `${humanise(d.kind)}: ${maskPii(d.text)}` })),
    ...file.alerts.map((a): TimelineItem => ({ at: a.created_at, kind: "alert", label: `Link alert ${a.alert_id} · ${pct(a.score)} · ${a.status}`, href: `/console/alerts/${encodeURIComponent(a.alert_id)}` })),
    features?.reviewed_at ? { at: features.reviewed_at, kind: "review", label: "MO features reviewed by an officer" } : null,
  ]);

  return (
    <div className="space-y-4">
      <Link href="/console/cases" className="text-sm text-muted hover:text-ink">← Cases</Link>

      <header className="rounded-xl border border-line bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-muted">{crime.crime_id}{crime.synthetic ? " · synthetic" : ""}</p>
            <h1 className="mt-1 text-2xl font-bold">{station.replace(/^PS-/, "")} FIR {crime.fir_no}</h1>
            <p className="text-muted">{humanise(crime.category)}{crime.sub_type ? ` · ${humanise(crime.sub_type)}` : ""} · severity {crime.severity}/5 · {humanise(crime.status)}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <a href="#evidence" className="rounded-md border border-line px-3 py-1.5 hover:bg-bg">Evidence ({file.evidence.length})</a>
            <Link href={`/console/map`} className="rounded-md border border-line px-3 py-1.5 hover:bg-bg">Pulse Map</Link>
            {canWrite && <AppealButton crimeId={crime.crime_id} />}
          </div>
        </div>
        <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[8rem_1fr_8rem_1fr]">
          <dt className="text-muted">Occurred</dt><dd>{fmt(crime.occurred_from)}{crime.occurred_to ? ` – ${fmt(crime.occurred_to)}` : ""}</dd>
          <dt className="text-muted">Reported</dt><dd>{fmt(crime.reported_at)}</dd>
          <dt className="text-muted">Place</dt><dd>{crime.address ?? "—"}{crime.ward_no ? ` · ward ${crime.ward_no}` : ""}</dd>
          <dt className="text-muted">Week</dt><dd>{crime.week ?? "—"}</dd>
          <dt className="text-muted">Sections</dt>
          <dd>{crime.sections.length ? crime.sections.map((s) => `${s.code}${s.ipc_equiv ? ` (${s.ipc_equiv})` : ""}`).join(", ") : "—"}</dd>
          <dt className="text-muted">Weapon</dt><dd>{humanise(crime.weapon)}</dd>
          <dt className="text-muted">Property</dt><dd>{crime.property.length ? crime.property.map((p) => describe(p)).join("; ") : "—"}</dd>
          <dt className="text-muted">Victims</dt><dd>{crime.victims.length ? crime.victims.map((v) => describe(v)).join("; ") : "—"}</dd>
        </dl>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Narrative">
            {crime.narrative ? <p className="whitespace-pre-wrap leading-relaxed">{maskPii(crime.narrative)}</p> : <Empty>No narrative recorded.</Empty>}
          </Card>

          <Card title="Described offenders" count={crime.offenders_described.length}>
            {crime.offenders_described.length === 0 ? <Empty>None described.</Empty> : (
              <ul className="space-y-1">{crime.offenders_described.map((o, i) => <li key={i}>{describe(o)}</li>)}</ul>
            )}
          </Card>

          <Card title="Statements" count={file.statements.length}>
            {file.statements.length === 0 ? <Empty>No statements yet.</Empty> : (
              <ul className="space-y-3">
                {file.statements.map((s) => (
                  <li key={s.statement_id} className="border-l-2 border-line pl-3">
                    <p className="text-xs text-muted">{s.witness_ref} · {humanise(s.mode)} · {fmt(s.recorded_at)}{s.transcript_model ? ` · transcribed by ${s.transcript_model}` : ""}</p>
                    {s.text ? <p className="mt-1 whitespace-pre-wrap">{maskPii(s.text)}</p> : <p className="mt-1 text-muted">Audio only{s.audio_path ? "" : " (file missing)"}.</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Vehicles" count={file.vehicles.length}>
            {file.vehicles.length === 0 ? <Empty>No vehicles recorded.</Empty> : (
              <table className="w-full">
                <thead className="text-left text-xs uppercase tracking-wider text-muted"><tr><th className="py-1">Role</th><th>Type</th><th>Make / model</th><th>Colour</th><th>Plate</th></tr></thead>
                <tbody>
                  {file.vehicles.map((v) => (
                    <tr key={v.id} className="border-t border-line">
                      <td className="py-1">{humanise(v.role)}</td><td>{humanise(v.vehicle_type)}</td><td>{v.make_model ?? "—"}</td><td>{v.colour ?? "—"}</td>
                      <td className="font-mono text-xs">{v.plate_pattern ? <Link href={`/console/search?q=${encodeURIComponent(v.plate_pattern)}`} className="text-signal hover:underline">{v.plate_pattern}</Link> : "unread"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Evidence" count={file.evidence.length} id="evidence">
            {file.evidence.length === 0 ? <Empty>No evidence uploaded yet.</Empty> : (
              <ul className="space-y-2">
                {file.evidence.map((e) => (
                  <li key={e.evidence_id} className="flex flex-wrap justify-between gap-2 border-t border-line pt-2 first:border-0 first:pt-0">
                    <span>{humanise(e.kind)}{e.camera_id ? ` · camera ${e.camera_id}` : ""} · captured {fmt(e.captured_at)}</span>
                    <span className="font-mono text-xs text-muted" title={e.sha256}>sha256 {e.sha256.slice(0, 12)}… · {e.custody.length} custody step{e.custody.length === 1 ? "" : "s"}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Persons" count={file.persons.length}>
            {file.persons.length === 0 ? <Empty>No persons linked.</Empty> : (
              <ul className="space-y-1">
                {file.persons.map((p) => (
                  <li key={`${p.person_id}-${p.role}`}><span className="font-semibold">{humanise(p.role)}</span> · <span className="font-mono text-xs">{p.person_id}</span>
                    {p.persons?.aliases?.length ? ` · aka ${p.persons.aliases.join(", ")}` : ""} · {describe(p.persons?.descriptors)}</li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Case diary" count={file.diary.length}>
            {file.diary.length === 0 ? <Empty>No diary entries yet.</Empty> : (
              <ul className="space-y-2">{file.diary.map((d) => <li key={d.entry_id}><span className="text-xs text-muted">{fmt(d.at)} · {humanise(d.kind)} · {d.author}</span><p>{maskPii(d.text)}</p></li>)}</ul>
            )}
          </Card>

          {file.forensics.length > 0 && (
            <Card title="Forensics" count={file.forensics.length}>
              <ul className="space-y-1">{file.forensics.map((f) => <li key={f.forensic_id}>{humanise(f.kind)} · match code <span className="font-mono text-xs">{f.match_code ?? "none"}</span> · {fmt(f.reported_at)}</li>)}</ul>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Extracted MO features">
            {!features ? (
              <div className="space-y-1">
                <p>Not extracted yet. The Extractor runs on the local pipeline after a case is filed.</p>
                {file.run ? (
                  <p className="text-muted">Latest run: {file.run.status} · {fmt(file.run.started)} · <Link href={`/console/system/trace/${encodeURIComponent(file.run.run_id)}`} className="text-signal hover:underline">trace</Link></p>
                ) : <p className="text-muted">Processing: no run has picked it up yet.</p>}
              </div>
            ) : (
              <div className="space-y-3">
                <dl className="grid grid-cols-[7.5rem_1fr] gap-y-1">
                  {moRows(features.mo).map(([k, v]) => <Fragment key={k}><dt className="text-muted">{humanise(k)}</dt><dd>{v}</dd></Fragment>)}
                </dl>
                {features.visual_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">{features.visual_tags.map((t) => <span key={t} className="rounded bg-bg px-1.5 py-0.5 text-xs">{humanise(t)}</span>)}</div>
                )}
                <p className="text-xs text-muted">
                  {features.model} · {features.extractor_version}{features.confidence !== null ? ` · confidence ${pct(features.confidence)}` : ""}
                  {features.receipt_id ? <> · receipt <span className="font-mono">{features.receipt_id.slice(0, 18)}…</span></> : null}
                  {file.run ? <> · <Link href={`/console/system/trace/${encodeURIComponent(file.run.run_id)}`} className="text-signal hover:underline">trace</Link></> : null}
                </p>
                <p className="text-xs text-muted">{features.reviewed_at ? `Reviewed by an officer on ${fmt(features.reviewed_at)}.` : "Not reviewed by an officer yet."}</p>
              </div>
            )}
          </Card>

          <Card title="Linked alerts" count={file.alerts.length}>
            {file.alerts.length === 0 ? <Empty>No link alerts involve this case yet.</Empty> : (
              <ul className="space-y-3">
                {file.alerts.map((a) => {
                  const others = a.crimes.filter((id) => id !== crime.crime_id);
                  return (
                    <li key={a.alert_id} className="flex gap-3">
                      <ScoreRing score={a.score} band={a.band} size={44} />
                      <div className="min-w-0">
                        <Link href={`/console/alerts/${encodeURIComponent(a.alert_id)}`} className="font-semibold text-signal hover:underline">{a.alert_id}</Link>
                        <div className="mt-0.5 flex flex-wrap gap-1"><BandPill band={a.band} /><StatusPill state={decisionState(a)} /></div>
                        <p className="mt-1 text-xs text-muted">with {others.map((id) => crimeTitle(briefs[id], id)).join(", ") || "—"}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          <Card title="Series" count={file.series.length}>
            {file.series.length === 0 ? <Empty>Not part of a detected series.</Empty> : (
              <ul className="space-y-1">
                {file.series.map((s) => <li key={s.series_id}><Link href={`/console/series/${encodeURIComponent(s.series_id)}`} className="text-signal hover:underline">{s.name}</Link> <span className="text-xs text-muted">· {s.status}</span></li>)}
              </ul>
            )}
          </Card>

          <Card title="Timeline" count={timeline.length}>
            <ol className="space-y-2 border-l border-line pl-3">
              {timeline.map((t, i) => (
                <li key={i}>
                  <p className="text-xs text-muted">{fmt(t.at)} · {t.kind}</p>
                  {t.href ? <Link href={t.href} className="text-signal hover:underline">{t.label}</Link> : <p>{t.label}</p>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
