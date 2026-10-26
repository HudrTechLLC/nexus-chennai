import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { stationNames } from "@/lib/alertsData";
import { fetchSeriesOverview } from "@/lib/seriesData";
import { STATUS_LABEL, isSeriesStatus, weekSpan, type SeriesStatus } from "@/lib/series";
import { shortStation } from "@/lib/stationMatrix";
import { Constellation, SeriesStatusPill } from "@/components/console/series/SeriesBits";

export const dynamic = "force-dynamic";

const FILTERS = ["all", "confirmed", "candidate", "closed"] as const;
type Filter = (typeof FILTERS)[number];

export default async function SeriesList({ searchParams }: { searchParams: { status?: string } }) {
  await requireOfficer("all");
  const filter: Filter = isSeriesStatus(searchParams.status) ? searchParams.status : "all";
  const sb = consoleServerClient();
  const { rows, error } = await fetchSeriesOverview(sb);
  const shown = filter === "all" ? rows : rows.filter((s) => s.status === filter);
  const names = await stationNames(sb, rows.flatMap((s) => s.stations));
  const count = (f: Filter) => (f === "all" ? rows.length : rows.filter((s) => s.status === f).length);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Series</h1>
        <p className="text-sm text-muted">
          Groups of linked cases the Series analyst found across stations. Each card shows where its cases fall in the city.
          Open one for the member cases, timeline, map and the Markovian dossier.
        </p>
      </div>

      <nav className="flex gap-1 border-b border-line" aria-label="Series status">
        {FILTERS.map((f) => (
          <Link
            key={f} href={f === "all" ? "/console/series" : `/console/series?status=${f}`} aria-current={f === filter ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${f === filter ? "border-signal font-semibold" : "border-transparent text-muted hover:text-ink"}`}
          >
            {f === "all" ? "All" : STATUS_LABEL[f as SeriesStatus]} <span className="font-mono text-xs text-muted">{count(f)}</span>
          </Link>
        ))}
      </nav>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load series: {error}</p>}
      {!error && shown.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
          {rows.length === 0
            ? "No series yet. The Series analyst creates them when the linking pipeline finds three or more connected cases; they appear here after the next batch run."
            : `No ${filter} series.`}
        </p>
      )}

      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((s) => (
          <li key={s.series_id}>
            <Link href={`/console/series/${encodeURIComponent(s.series_id)}`} className="flex h-full gap-4 rounded-xl border border-line bg-surface p-4 hover:border-signal">
              <Constellation cells={s.cells} />
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-semibold leading-tight">{s.name}</h2>
                  <SeriesStatusPill status={s.status} />
                </div>
                <p className="font-mono text-xs text-muted">{s.series_id}</p>
                <p className="text-sm">
                  <b className="tabular-nums">{s.members}</b> cases · <b className="tabular-nums">{s.stations.length}</b> station{s.stations.length === 1 ? "" : "s"}
                </p>
                <p className="truncate text-xs text-muted" title={s.stations.map((id) => names[id] ?? id).join(", ")}>
                  {s.stations.slice(0, 3).map((id) => shortStation(names[id] ?? id)).join(" · ")}
                  {s.stations.length > 3 ? ` +${s.stations.length - 3}` : ""}
                </p>
                <p className="text-xs text-muted">
                  {weekSpan(s.week_from, s.week_to)} · {s.categories.join(", ") || "—"}
                </p>
                <p className="text-xs">{s.has_dossier ? <span className="text-signal">Dossier ready</span> : <span className="text-muted">Dossier pending</span>}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
