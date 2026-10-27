import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { ROLE_LABEL, canDecideAlerts } from "@/lib/roles";
import { StartHereCard } from "@/components/console/StartHereCard";
import { ArrowRight, BellRing, FolderOpen, GitMerge, LayoutDashboard, ListChecks, Network, Percent, Users, Workflow } from "lucide-react";
import { Card, PageHeader, SectionHeader, StatTile, StatusPill } from "@/components/ui";
import {
  OPEN_STATUSES, alertFunnel, approvalRate, briefing, istIsoWeek, istMidnight, seriesCount, topSeries, weekKpis,
  type AlertRow, type SeriesRow,
} from "@/lib/overview";

export const dynamic = "force-dynamic";

/** PostgREST returns at most this many rows per request; the page says so if a list hits it. */
const ROW_CAP = 1000;

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
      <PageHeader
        icon={LayoutDashboard}
        title="Command overview"
        description={<>
          Signed in as {officer.name} · {ROLE_LABEL[officer.role]}
          {officer.stationId ? ` · ${officer.stationId}` : " · all stations"} ·{" "}
          {canDecideAlerts(officer.role) ? "can approve or reject link alerts" : "can read link alerts, including rejected ones"}
        </>}
      />
      {errors.length > 0 && <p role="alert" className="text-sm text-danger">Some figures could not load: {errors.join("; ")}</p>}

      <section aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile icon={FolderOpen} tone="info" label={`Open cases · ${scopeLabel}`} value={n(open.count)} emphasis={open.count === 0 ? "quiet" : "default"}
          sub={`registered or under investigation · ${n(undetected.count)} closed as undetected`} />
        <StatTile icon={BellRing} tone="signal" label="New link alerts · last 7 days" value={n(week.newAlerts)} sub="city-wide"
          emphasis={week.newAlerts === 0 ? "quiet" : "primary"} />
        <StatTile icon={Percent} tone="ok" label="Approval rate"
          value={rate.rate == null ? "—" : `${Math.round(rate.rate * 100)}%`}
          emphasis={rate.rate == null || rate.rate === 0 ? "quiet" : "default"}
          sub={rate.rate == null ? `nothing decided yet (${rate.approved} approved, ${rate.rejected} rejected)` : `${rate.approved} approved, ${rate.rejected} rejected`}
        />
        <StatTile icon={GitMerge} tone="accent" label="Cross-station links · last 7 days" value={n(week.crossStation)} sub="alerts spanning two or more stations"
          emphasis={week.crossStation === 0 ? "quiet" : "default"} />
        <StatTile icon={Users} tone="neutral" label="Joint task forces" value={n(taskforces.count)} sub="active"
          emphasis={!taskforces.count ? "quiet" : "default"} />
      </section>

      <StartHereCard sb={sb} officer={officer} alerts={alertRows} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionHeader icon={ListChecks} title="Today&apos;s briefing" description="Since 00:00 IST, counted from the records (not written by a model)." />
          <ul className="mt-4 space-y-1 text-sm">
            {lines.map((l) => (
              <li key={l.key}>
                <Link href={l.href} className={`group flex items-center gap-2 rounded-lg px-2 py-1.5 -mx-2 transition-colors hover:bg-surface-2 ${l.count === 0 ? "text-muted" : "text-ink"}`}>
                  <span aria-hidden className={`size-1.5 shrink-0 rounded-full ${l.count === 0 ? "bg-line" : "bg-signal"}`} />
                  <span className="underline-offset-2 group-hover:underline">{l.text}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <SectionHeader icon={Network} title="Alert funnel" description="Link alerts written by the agents, then approved by an analyst. Only pairs the Skeptic passed are stored as alerts; the pairs it dropped are in each run’s trace." />
          <ol className="mt-4 space-y-3">
            {[
              ["Alerts written", funnel.raised],
              ["Skeptic-approved", funnel.skepticApproved],
              ["Analyst-approved", funnel.analystApproved],
            ].map(([label, v]) => (
              <li key={label as string} className="flex items-center gap-3 text-sm">
                <span className="w-36 shrink-0">{label}</span>
                <span aria-hidden className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2 ring-1 ring-inset ring-line">
                  <span className="block h-full rounded-full bg-signal" style={{ width: `${funnel.raised ? Math.max(2, ((v as number) / funnel.raised) * 100) : 0}%` }} />
                </span>
                <span className="w-10 text-right font-medium tabular-nums">{v as number}</span>
              </li>
            ))}
          </ol>
          <Link href="/console/alerts" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-signal underline-offset-2 hover:underline">
            Open the alert inbox <ArrowRight className="size-4" aria-hidden />
          </Link>
        </Card>
      </div>

      <Card>
        <SectionHeader icon={Workflow} title="Top series" />
        {top.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No series yet. A series appears when the Linker groups three or more linked cases.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line text-sm">
            {top.map((s) => (
              <li key={s.series_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <Link href={`/console/series/${encodeURIComponent(s.series_id)}`} className="font-medium text-ink underline-offset-2 hover:underline">{s.name}</Link>
                {seriesCount(s.name, s.members) && <span className="text-muted">{seriesCount(s.name, s.members)}</span>}
                {s.status && <StatusPill status={s.status} />}
              </li>
            ))}
          </ul>
        )}
      </Card>
      {capped && <p className="text-xs text-muted">Some lists reached 1,000 rows; figures from them are a lower bound.</p>}
    </div>
  );
}
