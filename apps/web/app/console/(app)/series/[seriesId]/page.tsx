import Link from "next/link";
import { notFound } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { audit, crimeTitle } from "@/lib/alertsData";
import { pct } from "@/lib/alerts";
import { allows } from "@/lib/roles";
import { alertsTouching, briefsChunked, fetchMemberIds, fetchSeries, taskforcesFor } from "@/lib/seriesData";
import { dossierAuthor, memberLonLat, parseDossier, seriesHull, splitCitations, timeline, tokenSaving, type MemberPoint } from "@/lib/series";
import { BandPill, StatusPill } from "@/components/console/alerts/AlertBits";
import { SeriesStatusPill } from "@/components/console/series/SeriesBits";
import { SeriesMapLoader } from "@/components/console/series/SeriesMapLoader";
import type { SeriesMapPoint } from "@/components/console/series/SeriesMap";

export const dynamic = "force-dynamic";

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }) : null;

export default async function SeriesDetail({ params }: { params: { seriesId: string } }) {
  const officer = await requireOfficer("all");
  const seriesId = decodeURIComponent(params.seriesId);
  const sb = consoleServerClient();
  const series = await fetchSeries(sb, seriesId);
  if (!series) notFound();

  const memberIds = await fetchMemberIds(sb, seriesId);
  const [briefs, alerts, taskforces] = await Promise.all([
    briefsChunked(sb, memberIds),
    alertsTouching(sb, memberIds),
    taskforcesFor(sb, seriesId),
    audit(sb, "view", "series", seriesId),
  ]);

  const members: MemberPoint[] = memberIds.map((id) => briefs[id] ?? {
    crime_id: id, station_id: "", station_name: "—", category: "unknown", sub_type: null, fir_no: null,
    occurred_from: null, week: null, cell: null, lat: null, lon: null, full: false,
  });
  const ordered = timeline(members);
  const points: SeriesMapPoint[] = ordered.flatMap((m, i) => {
    const ll = memberLonLat(m);
    return ll ? [{ id: m.crime_id, p: ll.p, exact: ll.exact, label: crimeTitle(briefs[m.crime_id], m.crime_id), order: i }] : [];
  });
  const hull = seriesHull(points.map((x) => x.p));
  const stations = Array.from(new Set(members.map((m) => m.station_name).filter((s) => s !== "—")));
  const dossier = parseDossier(series.dossier);
  const cites = dossier ? splitCitations(dossier.cited_ids, memberIds) : null;
  const saving = dossier ? tokenSaving(dossier) : null;
  const hidden = members.filter((m) => !m.full).length;
  const isAdmin = allows(officer.role, "admin");

  return (
    <div className="space-y-5">
      <div>
        <Link href="/console/series" className="text-sm text-muted hover:text-ink">← Series</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold">{series.name}</h1>
          <SeriesStatusPill status={series.status} />
          {series.synthetic && <span className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">synthetic</span>}
        </div>
        <p className="mt-1 text-sm text-muted">
          <span className="font-mono text-xs">{series.series_id}</span> · {memberIds.length} cases · {stations.length} station{stations.length === 1 ? "" : "s"}
          {stations.length > 0 && <> ({stations.map((s) => s.replace(/^PS-/, "")).join(", ")})</>}
          {" "}· updated {fmt(series.updated_at)}
        </p>
        {hidden > 0 && (
          <p className="mt-1 text-xs text-muted">
            {hidden} member case{hidden === 1 ? " is" : "s are"} from other stations: you see the city-wide summary (category, week, H3 cell), not the FIR.
          </p>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="dossier">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="dossier" className="text-lg font-semibold">Series dossier</h2>
            <span className="font-mono text-xs uppercase tracking-widest text-accent">Markovian engine</span>
          </div>
          {!dossier ? (
            <p className="mt-3 rounded-lg border border-dashed border-line p-6 text-sm text-muted">
              Dossier pending. The Series analyst builds it with the Markovian engine: it reads every case, statement,
              evidence tag and screened tip of this series in bounded chunks, then writes the timeline, consistent MO,
              open leads and next steps here. The worker builds one series per pass, so it appears here shortly.
            </p>
          ) : (
            <>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                <div><dt className="text-muted">Records · chunks</dt><dd className="font-mono tabular-nums">{dossier.record_count ?? "?"} · {dossier.chunks}</dd></div>
                <div><dt className="text-muted">Tokens (projected → actual)</dt><dd className="font-mono tabular-nums">{dossier.tokens_projected ?? "?"} → {dossier.tokens_actual ?? "?"}</dd></div>
                <div><dt className="text-muted">Saving</dt><dd className="font-mono tabular-nums">{saving == null ? "—" : pct(saving)}</dd></div>
                <div><dt className="text-muted">Built</dt><dd>{fmt(dossier.generated_at) ?? "—"}</dd></div>
              </dl>
              <div className="prose prose-sm prose-slate mt-4 max-w-none dark:prose-invert">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{dossier.text}</ReactMarkdown>
              </div>
              {cites && (cites.crimes.length > 0 || cites.other.length > 0) && (
                <div className="mt-4 border-t border-line pt-3 text-xs">
                  <p className="text-muted">Cited records (the engine may cite only ids that exist):</p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {cites.crimes.map((id) => (
                      briefs[id]?.full
                        ? <Link key={id} href={`/console/cases/${encodeURIComponent(id)}`} className="rounded bg-signal-soft px-1.5 py-0.5 font-mono text-signal hover:underline">{id}</Link>
                        : <span key={id} className="rounded bg-bg px-1.5 py-0.5 font-mono">{id}</span>
                    ))}
                    {cites.other.map((id) => <span key={id} className="rounded bg-bg px-1.5 py-0.5 font-mono text-muted">{id}</span>)}
                  </p>
                </div>
              )}
              <p className="mt-3 font-mono text-[11px] text-muted">
                {(() => { const a = dossierAuthor(dossier); return a.model ? <>model {a.label} · </> : <span className="text-accent">{a.label} · </span>; })()}
                {dossier.receipt_ids.length > 0
                  ? <span title={dossier.receipt_ids.join(", ")}>{dossier.receipt_ids.length} receipt{dossier.receipt_ids.length === 1 ? "" : "s"} · </span>
                  : dossier.receipt_id && <>receipt {dossier.receipt_id} · </>}
                {dossier.run_id && (isAdmin
                  ? <Link href={`/console/system/trace/${encodeURIComponent(dossier.run_id)}`} className="text-signal hover:underline">run {dossier.run_id}</Link>
                  : <>run {dossier.run_id}</>)}
              </p>
            </>
          )}
        </section>

        <div className="space-y-5">
          <section aria-labelledby="map">
            <h2 id="map" className="mb-2 text-lg font-semibold">Map</h2>
            <SeriesMapLoader points={points} hull={hull} />
          </section>

          <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="tf">
            <h2 id="tf" className="text-lg font-semibold">Joint task force</h2>
            {taskforces.length === 0
              ? <p className="mt-2 text-sm text-muted">No joint task force has been opened on this series.</p>
              : (
                <ul className="mt-2 space-y-1 text-sm">
                  {taskforces.map((t) => (
                    <li key={t.taskforce_id}>
                      <b>{t.name}</b> <span className="font-mono text-xs text-muted">{t.taskforce_id}</span> · {t.status}
                    </li>
                  ))}
                </ul>
              )}
          </section>
        </div>
      </div>

      <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="timeline">
        <h2 id="timeline" className="text-lg font-semibold">Member cases · timeline</h2>
        {ordered.length === 0 ? (
          <p className="mt-2 text-sm text-muted">This series has no member cases recorded.</p>
        ) : (
          <ol className="mt-3 space-y-0">
            {ordered.map((m, i) => (
              <li key={m.crime_id} className="relative grid grid-cols-[2rem_1fr] gap-3 pb-3">
                <span className="flex flex-col items-center">
                  <span className="grid h-6 w-6 place-items-center rounded-full bg-signal-soft font-mono text-[11px] text-signal">{i + 1}</span>
                  {i < ordered.length - 1 && <span className="w-px flex-1 bg-line" aria-hidden />}
                </span>
                <div className="text-sm">
                  <div className="flex flex-wrap items-baseline gap-x-3">
                    {m.full
                      ? <Link href={`/console/cases/${encodeURIComponent(m.crime_id)}`} className="font-semibold text-signal hover:underline">{crimeTitle(briefs[m.crime_id], m.crime_id)}</Link>
                      : <span className="font-semibold">{crimeTitle(briefs[m.crime_id], m.crime_id)}</span>}
                    <span className="text-muted">{m.category.replace(/_/g, " ")}{m.sub_type ? ` · ${m.sub_type.replace(/_/g, " ")}` : ""}</span>
                  </div>
                  <p className="text-xs text-muted">
                    {fmt(m.occurred_from) ?? (m.week ? `week ${m.week}` : "time not visible")}
                    {m.gapDays != null && i > 0 && <> · {m.gapDays} day{m.gapDays === 1 ? "" : "s"} after #{i}</>}
                    {!m.full && " · city-wide summary"}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="rounded-xl border border-line bg-surface p-5" aria-labelledby="links">
        <h2 id="links" className="text-lg font-semibold">Link alerts on these cases</h2>
        {alerts.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No link alerts touch these cases yet. The Linker&apos;s pair alerts on member cases are listed here as they are raised.</p>
        ) : (
          <ul className="mt-2 divide-y divide-line">
            {alerts.map((a) => (
              <li key={a.alert_id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <Link href={`/console/alerts/${encodeURIComponent(a.alert_id)}`} className="font-mono text-xs text-signal hover:underline">{a.alert_id}</Link>
                <span className="font-mono tabular-nums">{pct(a.score)}</span>
                <BandPill band={a.band} />
                <StatusPill state={a.status} />
                <span className="text-xs text-muted">{a.kind} · {a.crimes.length} cases</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
