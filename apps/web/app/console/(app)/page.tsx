import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { ROLE_LABEL, canDecideAlerts } from "@/lib/roles";
import { StartHereCard } from "@/components/console/StartHereCard";
import {
  OPEN_STATUSES, alertFunnel, approvalRate, briefing, istIsoWeek, istMidnight, seriesCount, topSeries, weekKpis,
  type AlertRow, type SeriesRow,
} from "@/lib/overview";

export const dynamic = "force-dynamic";

/** PostgREST returns at most this many rows per request; the page says so if a list hits it. */
const ROW_CAP = 1000;

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-muted">{sub}</div>
    </div>
  );
}

/**
 * Command overview (spec G2 `/console`, DASH-07, WS3-15): KPIs, alert funnel, top series and a
 * code-generated "today's briefing". Read-only; every number comes from rows the viewer may read.
 */
export default async function Overview({ searchParams }: { searchParams: { denied?: string } }) {
  const officer = await requireOfficer();
  const sb = consoleServerClient();
  const now = new Date();
  const midnight = istMidnight(now).toISOString();
  const ownStation = officer.role === "station_officer" && officer.stationId ? officer.stationId : null;
  const scoped = <T extends { eq: (c: string, v: string) => T }>(q: T) => (ownStation ? q.eq("station_id", ownStation) : q);

  const [open, undetected, firs, alerts, taskforces, series, members, tips, decisions] = await Promise.all([
    scoped(sb.from("crimes").select("crime_id", { count: "exact", head: true }).in("status", [...OPEN_STATUSES])),
    scoped(sb.from("crimes").select("crime_id", { count: "exact", head: true }).eq("status", "undetected")),
    scoped(sb.from("crimes").select("crime_id", { count: "exact", head: true }).gte("reported_at", midnight)),
    sb.from("link_alerts").select("alert_id, kind, stations, status, skeptic, created_at").order("created_at", { ascending: false }).limit(ROW_CAP),
    sb.from("taskforces").select("taskforce_id", { count: "exact", head: true }).eq("status", "active"),
    sb.from("series").select("series_id, name, status, created_at").limit(ROW_CAP),
    sb.from("series_members").select("series_id").limit(ROW_CAP),
    sb.from("tips").select("tip_id", { count: "exact", head: true }).eq("received_week", istIsoWeek(now)),
    sb.from("alert_decisions").select("at, decision").gte("at", midnight).limit(ROW_CAP),
  ]);

  const alertRows = (alerts.data ?? []) as AlertRow[];
  const seriesRows = (series.data ?? []) as SeriesRow[];
  const week = weekKpis(alertRows, now);
  const rate = approvalRate(alertRows);
  const funnel = alertFunnel(alertRows);
  const top = topSeries(seriesRows, (members.data ?? []) as { series_id: string }[]);
  const lines = briefing({
    alerts: alertRows, firsToday: firs.count ?? 0, firsStation: ownStation, tipsThisWeek: tips.count ?? 0, series: seriesRows,
    decisions: (decisions.data ?? []) as { at: string; decision: string }[], now,
  });
  const errors = [open, undetected, firs, alerts, taskforces, series, members, tips, decisions].map((r) => r.error?.message).filter(Boolean);
  const capped = [alerts, series, members].some((r) => (r.data?.length ?? 0) >= ROW_CAP);
  const scopeLabel = ownStation ? `your station (${ownStation})` : "city-wide";
  const n = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("en-IN"));

  return (
    <div className="space-y-6">
      {searchParams.denied && (
        <p className="rounded-md border border-accent bg-accent-soft px-3 py-2 text-sm">
          Your role ({ROLE_LABEL[officer.role]}) cannot open that screen.
        </p>
      )}
      <div>
        <h1 className="text-2xl font-bold">Command overview</h1>
        <p className="text-sm text-muted">
          Signed in as {officer.name} · {ROLE_LABEL[officer.role]}
          {officer.stationId ? ` · ${officer.stationId}` : " · all stations"} ·{" "}
          {canDecideAlerts(officer.role) ? "can approve or reject link alerts" : "can read link alerts, including rejected ones"}
        </p>
      </div>
      {errors.length > 0 && <p role="alert" className="text-sm text-red-600">Some figures could not load: {errors.join("; ")}</p>}

      <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Tile label={`Open cases · ${scopeLabel}`} value={n(open.count)} sub={`registered or under investigation · ${n(undetected.count)} closed as undetected`} />
        <Tile label="New link alerts · last 7 days" value={n(week.newAlerts)} sub="city-wide" />
        <Tile
          label="Approval rate"
          value={rate.rate == null ? "—" : `${Math.round(rate.rate * 100)}%`}
          sub={rate.rate == null ? `nothing decided yet (${rate.approved} approved, ${rate.rejected} rejected)` : `${rate.approved} approved, ${rate.rejected} rejected`}
        />
        <Tile label="Cross-station links · last 7 days" value={n(week.crossStation)} sub="alerts spanning two or more stations" />
        <Tile label="Joint task forces" value={n(taskforces.count)} sub="active" />
      </section>

      <StartHereCard sb={sb} officer={officer} alerts={alertRows} />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-1 font-semibold">Today&apos;s briefing</h2>
          <p className="mb-3 text-xs text-muted">Since 00:00 IST, counted from the records (not written by a model).</p>
          <ul className="space-y-2 text-sm">
            {lines.map((l) => (
              <li key={l.key}>
                <Link href={l.href} className={`underline-offset-2 hover:underline ${l.count === 0 ? "text-muted" : ""}`}>{l.text}</Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-1 font-semibold">Alert funnel</h2>
          <p className="mb-3 text-xs text-muted">Link alerts written by the agents, then approved by an analyst. Only pairs the Skeptic passed are stored as alerts; the pairs it dropped are in each run’s trace.</p>
          <ol className="space-y-2">
            {[
              ["Alerts written", funnel.raised],
              ["Skeptic-approved", funnel.skepticApproved],
              ["Analyst-approved", funnel.analystApproved],
            ].map(([label, v]) => (
              <li key={label as string} className="flex items-center gap-3 text-sm">
                <span className="w-36 shrink-0">{label}</span>
                <span className="h-3 rounded bg-signal" style={{ width: `${funnel.raised ? Math.max(2, ((v as number) / funnel.raised) * 100) : 0}%`, maxWidth: "60%" }} aria-hidden />
                <span className="tabular-nums">{v as number}</span>
              </li>
            ))}
          </ol>
          <Link href="/console/alerts" className="mt-3 inline-block text-xs underline-offset-2 hover:underline">Open the alert inbox</Link>
        </section>
      </div>

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Top series</h2>
        {top.length === 0 ? (
          <p className="text-sm text-muted">No series yet. A series appears when the Linker groups three or more linked cases.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {top.map((s) => (
              <li key={s.series_id}>
                <Link href={`/console/series/${encodeURIComponent(s.series_id)}`} className="underline-offset-2 hover:underline">{s.name}</Link>
                <span className="text-muted"> · {[seriesCount(s.name, s.members), s.status].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {capped && <p className="text-xs text-muted">Some lists reached 1,000 rows; figures from them are a lower bound.</p>}
    </div>
  );
}
