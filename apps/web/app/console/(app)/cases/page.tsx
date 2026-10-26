import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { allows } from "@/lib/roles";
import { CASE_STATUSES, CATEGORIES, casesHref, humanise, PAGE_SIZE, parseCaseFilters } from "@/lib/cases";
import { fetchCases, PLATE_CAP, stationOptions } from "@/lib/casesData";

export const dynamic = "force-dynamic";

function fmt(at: string) {
  return new Date(at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

const input = "rounded-md border border-line bg-bg px-2 py-1.5 text-sm";

/** Case list with filters (spec G2 /console/cases). Station officers see their own station's cases (RLS). */
export default async function CasesPage({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const officer = await requireOfficer("all");
  const f = parseCaseFilters(searchParams);
  const sb = consoleServerClient();
  const [{ rows, total, error, capped }, stations] = await Promise.all([fetchCases(sb, f), stationOptions(sb)]);
  const names = Object.fromEntries(stations.map((s) => [s.station_id, s.name]));
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const ownOnly = officer.role === "station_officer";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Cases</h1>
          <p className="text-sm text-muted">
            {ownOnly
              ? `Cases registered at ${names[officer.stationId ?? ""] ?? "your station"}. Other stations' cases appear in alerts and on the map as city-wide summaries.`
              : "Every station's cases. Filter, or use Search for one box across all sources."}
          </p>
        </div>
        {allows(officer.role, ["station_officer", "admin"]) && (
          <Link href="/console/cases/new" className="rounded-md bg-ink px-3 py-2 text-sm font-semibold text-bg hover:opacity-90">
            File a new FIR
          </Link>
        )}
      </div>

      <form method="get" className="grid gap-2 rounded-xl border border-line bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Filter cases">
        {!ownOnly && (
          <label className="grid gap-1 text-xs text-muted">Station
            <select name="station" defaultValue={f.station ?? ""} className={input}>
              <option value="">All stations</option>
              {stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.name}</option>)}
            </select>
          </label>
        )}
        <label className="grid gap-1 text-xs text-muted">Category
          <select name="category" defaultValue={f.category ?? ""} className={input}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{humanise(c)}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted">Status
          <select name="status" defaultValue={f.status ?? ""} className={input}>
            <option value="">Any status</option>
            {CASE_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-muted">FIR no.
          <input name="fir" defaultValue={f.fir ?? ""} placeholder="1182/2026" className={input} />
        </label>
        <label className="grid gap-1 text-xs text-muted">Occurred from
          <input type="date" name="from" defaultValue={f.from ?? ""} className={input} />
        </label>
        <label className="grid gap-1 text-xs text-muted">Occurred to
          <input type="date" name="to" defaultValue={f.to ?? ""} className={input} />
        </label>
        <label className="grid gap-1 text-xs text-muted">Vehicle plate (? = unread)
          <input name="plate" defaultValue={f.plate ?? ""} placeholder="TN09??4471" className={`${input} font-mono`} />
        </label>
        <div className="flex items-end gap-2">
          <button className="rounded-md bg-ink px-3 py-1.5 text-sm font-semibold text-bg">Apply</button>
          <Link href="/console/cases" className="px-2 py-1.5 text-sm text-muted hover:text-ink">Clear</Link>
        </div>
      </form>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load cases: {error}</p>}

      <p className="text-sm text-muted">{total.toLocaleString("en-IN")} case{total === 1 ? "" : "s"}{pages > 1 ? ` · page ${f.page} of ${pages}` : ""}
        {capped ? ` · the plate matched more than ${PLATE_CAP} vehicles, so only the first ${PLATE_CAP} are used; type more characters to narrow it` : ""}</p>

      {!error && rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">No cases match these filters.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-3 py-2">FIR</th>
                <th className="px-3 py-2">Station</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Occurred</th>
                <th className="px-3 py-2">Place</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.crime_id} className="border-b border-line last:border-0 hover:bg-bg">
                  <td className="px-3 py-2">
                    <Link href={`/console/cases/${encodeURIComponent(c.crime_id)}`} className="font-semibold text-signal hover:underline">{c.fir_no}</Link>
                    <div className="font-mono text-xs text-muted">{c.crime_id}</div>
                  </td>
                  <td className="px-3 py-2">{names[c.station_id] ?? c.station_id}</td>
                  <td className="px-3 py-2">{humanise(c.category)}{c.sub_type ? <span className="text-muted"> · {humanise(c.sub_type)}</span> : null}</td>
                  <td className="whitespace-nowrap px-3 py-2">{fmt(c.occurred_from)}</td>
                  <td className="px-3 py-2 text-muted">{c.address ?? "—"}</td>
                  <td className="px-3 py-2">{humanise(c.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <nav className="flex justify-between text-sm" aria-label="Pages">
          {f.page > 1 ? <Link href={casesHref({ ...f, page: f.page - 1 })} className="text-signal hover:underline">← Newer</Link> : <span />}
          {f.page < pages ? <Link href={casesHref({ ...f, page: f.page + 1 })} className="text-signal hover:underline">Older →</Link> : <span />}
        </nav>
      )}
    </div>
  );
}
