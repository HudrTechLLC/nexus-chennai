import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import {
  DATA_SOURCES, DQ_LABEL, MIRROR_TABLES, SOURCE_TYPES, dqFor, sourceNumber, unifiedDq, zetarisCounts, type StatusRow,
} from "@/lib/dataSources";

export const dynamic = "force-dynamic";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "—";
const fmt = (n: number) => n.toLocaleString("en-IN");

/**
 * Data sources (WS3-27): every source Zetaris federates into the unified views, with the numbers the
 * database holds for it. Vercel cannot reach Zetaris (D-019), so this page reads only Supabase: table
 * counts, and the system_status rows the Zetaris jobs write. Nothing here is hard-coded.
 */
export default async function DataSourcesPage() {
  await requireOfficer("admin");
  const sb = consoleServerClient();
  const head = (table: string) => sb.from(table).select("*", { count: "exact", head: true });
  const [status, stations, stationsWithFirs, ...mirrors] = await Promise.all([
    sb.from("system_status").select("component, state, detail, checked_at").in("component", ["zetaris", "zetaris:dq", "zetaris:sources"]),
    head("stations"),
    sb.from("stations").select("station_id, crimes!inner(crime_id)", { count: "exact", head: true }),
    ...MIRROR_TABLES.map(head),
  ]);
  const rows = (status.data ?? []) as StatusRow[];
  const row = (c: string) => rows.find((r) => r.component === c);
  const zetaris = row("zetaris");
  const dq = row("zetaris:dq");
  const zSources = row("zetaris:sources");
  const zCounts = zetarisCounts(zSources);
  const mirrorCounts = Object.fromEntries(MIRROR_TABLES.map((t, i) => [t, mirrors[i].error ? null : mirrors[i].count ?? null]));
  const silos = stationsWithFirs.error ? null : stationsWithFirs.count;
  const unified = Object.entries(unifiedDq(dq));
  const loadError = status.error ?? stations.error ?? stationsWithFirs.error ?? mirrors.find((m) => m.error)?.error;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/console/system" className="text-sm text-muted underline-offset-2 hover:underline">← System</Link>
        <h1 className="mt-1 text-2xl font-bold">Data sources</h1>
        <p className="mt-1 text-lg">
          {silos !== null ? `${fmt(silos)} station silos` : "Every station silo"} and {SOURCE_TYPES.length} source types,
          federated by Zetaris into one view.
        </p>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Each station files its own records, and the older systems, cameras, emergency calls and open feeds each keep
          theirs. Zetaris reads them where they live and joins them into the unified crime view
          (<span className="font-mono text-xs">v_crime_unified</span>) and the case bundle
          (<span className="font-mono text-xs">case_bundle_v</span>) the agents work from. This page cannot reach Zetaris
          directly, so it shows what the database holds: table counts, and the counts the Zetaris jobs last wrote.
        </p>
      </div>

      {loadError && <p role="alert" className="text-sm text-red-600">Some numbers could not be loaded: {loadError.message}</p>}

      <section className="grid gap-3 sm:grid-cols-3">
        <Stat label="Stations in the registry" value={stations.error ? "—" : fmt(stations.count ?? 0)}
          sub={silos !== null ? `${fmt(silos)} with FIRs in the current system` : undefined} />
        <Stat label="Zetaris last answered" value={when(zetaris?.checked_at ?? null)} sub={zetaris ? `state: ${zetaris.state}` : "no heartbeat yet"} />
        <Stat label="Data-quality counts as of" value={when(dq?.checked_at ?? null)} sub={dq ? "from the Zetaris DQ views" : "not run yet"} />
      </section>

      {unified.length > 0 && (
        <section className="rounded-xl border border-line bg-surface p-5">
          <h2 className="font-semibold">Checks on the unified crime view</h2>
          <p className="mt-1 text-sm text-muted">
            Run over <span className="font-mono text-xs">v_crime_unified</span>, so current FIRs and the legacy exports are
            checked together, across stations.
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {unified.map(([rule, n]) => (
              <li key={rule} className={`rounded-full border px-2 py-0.5 text-xs ${n > 0 ? "border-accent text-accent" : "border-line text-muted"}`}>
                {fmt(n)} {DQ_LABEL[rule] ?? rule}
              </li>
            ))}
          </ul>
        </section>
      )}

      {SOURCE_TYPES.map((type) => (
        <section key={type} className="rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">{type}</h2>
          <ul className="grid gap-3 lg:grid-cols-2">
            {DATA_SOURCES.filter((s) => s.type === type).map((s) => {
              const num = sourceNumber(s, zCounts, zSources?.checked_at ?? null, mirrorCounts);
              const flags = Object.entries(dqFor(s, dq));
              return (
                <li key={s.id} className="rounded-lg border border-line p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium">{s.label}</div>
                      <div className="font-mono text-xs text-muted">{s.id} · {s.store}</div>
                    </div>
                    <div className="text-right">
                      {num.kind === "live-only" ? (
                        <div className="text-sm text-muted">read live through Zetaris</div>
                      ) : (
                        <div className="text-lg font-semibold tabular-nums">{fmt(num.n)}</div>
                      )}
                      {num.kind === "zetaris" && <div className="text-xs text-muted">rows as of {when(num.asOf)}, via Zetaris</div>}
                      {num.kind === "mirror" && <div className="text-xs text-muted">{num.note ?? "rows"} · <span className="font-mono">{num.table}</span></div>}
                    </div>
                  </div>
                  <p className="mt-2 text-sm">{s.what}</p>
                  {s.stationScoped && s.id === "sb.crimes" && silos !== null && (
                    <p className="mt-1 text-xs text-muted">Covers {fmt(silos)} station silos.</p>
                  )}
                  {s.stationScoped && s.id !== "sb.crimes" && (
                    <p className="mt-1 text-xs text-muted">Filed by station; station coverage is read live through Zetaris.</p>
                  )}
                  {flags.length > 0 && (
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {flags.map(([rule, n]) => (
                        <li key={rule} className={`rounded-full border px-2 py-0.5 text-xs ${n > 0 ? "border-accent text-accent" : "border-line text-muted"}`}>
                          {fmt(n)} {DQ_LABEL[rule] ?? rule}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted">
                    Feeds
                    {s.feeds.map((f) => <span key={f} className="rounded bg-bg px-1.5 py-0.5 font-mono">{f}</span>)}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <p className="text-xs text-muted">
        Counts marked with a table name are rows in that Supabase table; a &ldquo;map projection&rdquo; is a summary kept for
        the maps, not the raw source. Data-quality counts are as of the time above.
      </p>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
