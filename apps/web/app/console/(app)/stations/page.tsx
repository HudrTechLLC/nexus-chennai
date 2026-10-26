import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { fetchStationMatrix } from "@/lib/seriesData";
import { buildMatrix, cellCounts, intensity, pairKey, parseStatuses, shortStation, type PairCounts } from "@/lib/stationMatrix";
import type { AlertStatus } from "@/lib/alerts";

export const dynamic = "force-dynamic";

const WINDOWS = { "7": 7, "30": 30, all: null } as const;
type Win = keyof typeof WINDOWS;
const ALL_STATUSES: AlertStatus[] = ["approved", "pending", "rejected"];
const STATUS_LABEL: Record<AlertStatus, string> = { approved: "Approved", pending: "Pending", rejected: "Rejected" };

function breakdown(c: PairCounts) {
  return `${c.total} alert${c.total === 1 ? "" : "s"}: ${c.approved} approved, ${c.pending} pending, ${c.rejected} rejected`;
}

export default async function StationsPage({ searchParams }: { searchParams: { status?: string; days?: string; a?: string; b?: string } }) {
  await requireOfficer("supervisor+");
  const statuses = parseStatuses(searchParams.status);
  const win: Win = searchParams.days === "7" || searchParams.days === "30" ? searchParams.days : "all";
  const days = WINDOWS[win];
  const since = days ? new Date(Date.now() - days * 86_400_000).toISOString() : null;

  const sb = consoleServerClient();
  const { payload, error } = await fetchStationMatrix(sb, since);
  const m = buildMatrix(payload, statuses);
  const name = (id: string) => m.stations.find((s) => s.id === id)?.name ?? payload.stations.find((s) => s.id === id)?.name ?? id;

  const qs = (over: Partial<{ status: string; days: string; a: string; b: string }>) => {
    const p = new URLSearchParams();
    const status = over.status ?? (statuses.length === 3 ? "" : statuses.join(","));
    if (status) p.set("status", status);
    const d = over.days ?? (win === "all" ? "" : win);
    if (d && d !== "all") p.set("days", d);
    if (over.a) p.set("a", over.a);
    if (over.b) p.set("b", over.b);
    const s = p.toString();
    return s ? `/console/stations?${s}` : "/console/stations";
  };
  const toggle = (st: AlertStatus) => {
    const next = statuses.includes(st) ? statuses.filter((x) => x !== st) : [...statuses, st];
    return qs({ status: next.length === 0 || next.length === 3 ? "" : ALL_STATUSES.filter((x) => next.includes(x)).join(",") });
  };

  const sel = searchParams.a && searchParams.b ? { a: searchParams.a, b: searchParams.b, c: cellCounts(m, searchParams.a, searchParams.b) } : null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Stations · link matrix</h1>
        <p className="text-sm text-muted">
          Which stations&apos; cases the pipeline linked to which. Each cell counts link alerts between two stations; the
          diagonal counts alerts inside one station. Darker means more links. Open a cell for its alerts.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <div className="flex gap-1" role="group" aria-label="Alert status">
          {ALL_STATUSES.map((st) => (
            <Link key={st} href={toggle(st)} aria-pressed={statuses.includes(st)}
              className={`rounded-full border px-2.5 py-0.5 ${statuses.includes(st) ? "border-signal bg-signal-soft text-signal" : "border-line text-muted hover:text-ink"}`}>
              {STATUS_LABEL[st]}
            </Link>
          ))}
        </div>
        <div className="flex gap-1" role="group" aria-label="Time window">
          {(Object.keys(WINDOWS) as Win[]).map((w) => (
            <Link key={w} href={qs({ days: w })} aria-current={w === win ? "true" : undefined}
              className={`rounded-md px-2 py-0.5 ${w === win ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>
              {w === "all" ? "All time" : `Last ${w} days`}
            </Link>
          ))}
        </div>
        <span className="text-xs text-muted">{payload.alerts} alerts in window · {m.crossTotal} cross-station links</span>
      </div>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load the matrix: {error}</p>}
      {!error && m.stations.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
          No link alerts {days ? `in the last ${days} days` : "yet"} for the chosen statuses.
          Each alert the Linker raises between two stations&apos; cases adds one to their cell, and links inside one station sit on the diagonal.
          {(days || statuses.length < 3) && " Try “All time” and every status."}
        </p>
      )}

      {m.stations.length > 0 && (
        <div className="grid gap-5 xl:grid-cols-[1fr_20rem]">
          <div className="overflow-auto rounded-xl border border-line bg-surface p-3">
            <table className="border-separate border-spacing-0.5 text-xs">
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-20 bg-surface" />
                  {m.stations.map((s) => (
                    <th key={s.id} scope="col" className="sticky top-0 z-10 h-28 min-w-[1.75rem] bg-surface align-bottom font-normal text-muted">
                      <span className="inline-block origin-bottom-left translate-x-3 -rotate-45 whitespace-nowrap" title={s.name}>{shortStation(s.name)}</span>
                    </th>
                  ))}
                  <th scope="col" className="sticky top-0 bg-surface px-2 align-bottom font-semibold">Total</th>
                </tr>
              </thead>
              <tbody>
                {m.stations.map((row) => (
                  <tr key={row.id}>
                    <th scope="row" className="sticky left-0 z-10 whitespace-nowrap bg-surface pr-2 text-right font-normal" title={row.name}>
                      {shortStation(row.name)} {row.zone && <span className="text-muted">· {row.zone}</span>}
                    </th>
                    {m.stations.map((col) => {
                      const c = cellCounts(m, row.id, col.id);
                      const diag = row.id === col.id;
                      const t = intensity(c.total, diag ? Math.max(c.total, m.maxCross) : m.maxCross);
                      const active = sel && pairKey(sel.a, sel.b) === pairKey(row.id, col.id);
                      const tint = diag ? "var(--accent)" : "var(--signal)";
                      return (
                        <td key={col.id} className="p-0">
                          {c.total > 0 ? (
                            <Link href={qs({ a: row.id, b: col.id })} title={`${shortStation(row.name)} ↔ ${shortStation(col.name)}: ${breakdown(c)}`}
                              className={`grid h-7 w-7 place-items-center rounded font-mono tabular-nums ${active ? "ring-2 ring-ink" : ""}`}
                              style={{ background: `color-mix(in srgb, ${tint} ${Math.round(15 + t * 70)}%, var(--surface))`, color: t > 0.55 ? "var(--surface)" : "var(--ink)" }}>
                              {c.total}
                            </Link>
                          ) : (
                            <span className="block h-7 w-7 rounded bg-bg" aria-hidden />
                          )}
                        </td>
                      );
                    })}
                    <td className="px-2 text-right font-mono tabular-nums">{m.perStation[row.id]?.total ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <aside className="space-y-4">
            {sel && (
              <section className="rounded-xl border border-signal bg-surface p-4">
                <h2 className="font-semibold">{shortStation(name(sel.a))}{sel.a !== sel.b && <> ↔ {shortStation(name(sel.b))}</>}</h2>
                <p className="text-xs text-muted">{breakdown(sel.c)}</p>
                {sel.c.alertIds.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">No alerts for this pair with the current filters.</p>
                ) : (
                  <ul className="mt-2 space-y-1">
                    {sel.c.alertIds.map((id) => (
                      <li key={id}><Link href={`/console/alerts/${encodeURIComponent(id)}`} className="font-mono text-xs text-signal hover:underline">{id}</Link></li>
                    ))}
                  </ul>
                )}
                {sel.c.alertIds.length < sel.c.total && <p className="mt-2 text-xs text-muted">Showing the newest {sel.c.alertIds.length} per status.</p>}
                <Link href={qs({})} className="mt-3 inline-block text-xs text-muted hover:text-ink">Close</Link>
              </section>
            )}
            <section className="rounded-xl border border-line bg-surface p-4">
              <h2 className="font-semibold">Most-linked station pairs</h2>
              {m.topPairs.length === 0 ? (
                <p className="mt-2 text-sm text-muted">No cross-station links with these filters.</p>
              ) : (
                <ol className="mt-2 space-y-1.5 text-sm">
                  {m.topPairs.slice(0, 10).map((p) => (
                    <li key={`${p.a}|${p.b}`} className="flex items-baseline justify-between gap-2">
                      <Link href={qs({ a: p.a, b: p.b })} className="truncate hover:text-signal">{shortStation(name(p.a))} ↔ {shortStation(name(p.b))}</Link>
                      <span className="shrink-0 font-mono text-xs tabular-nums text-muted" title={breakdown(p.counts)}>
                        {p.counts.total} <span className="text-signal">({p.counts.approved}✓)</span>
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </aside>
        </div>
      )}
    </div>
  );
}
