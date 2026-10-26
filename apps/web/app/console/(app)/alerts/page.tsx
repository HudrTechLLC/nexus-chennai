import Link from "next/link";
import { requireOfficer } from "@/lib/auth";
import { consoleServerClient } from "@/lib/supabase/server";
import { parseScope, parseSort, parseTab, sortAlerts, TAB_LABEL, TABS, SORTS, type Scope } from "@/lib/alerts";
import { crimeBriefs, fetchInbox, officerNames } from "@/lib/alertsData";
import { canDecideAlerts } from "@/lib/roles";
import { AlertCard } from "@/components/console/alerts/AlertCard";
import { AlertsLive } from "@/components/console/alerts/AlertsLive";

export const dynamic = "force-dynamic";

const SORT_LABEL = { score: "Score", newest: "Newest", stations: "Stations" } as const;

export default async function AlertsInbox({ searchParams }: { searchParams: { tab?: string; sort?: string; scope?: string } }) {
  const officer = await requireOfficer("all");
  const tab = parseTab(searchParams.tab);
  const sort = parseSort(searchParams.sort);
  const scope = parseScope(searchParams.scope, officer.role, officer.stationId);
  const canScope = officer.role === "station_officer" && !!officer.stationId;
  const sb = consoleServerClient();

  const { rows, error } = await fetchInbox(sb, officer, tab, scope);
  const alerts = sortAlerts(rows, sort);
  const crimes = await crimeBriefs(sb, alerts.flatMap((a) => a.crimes));
  const deciderNames = await officerNames(sb, alerts.flatMap((a) => (a.alert_decisions ?? []).map((d) => d.by)));

  const href = (t: string, s: string, sc: Scope = scope) => `/console/alerts?tab=${t}&sort=${s}${canScope ? `&scope=${sc}` : ""}`;

  return (
    <div className="space-y-4">
      <AlertsLive />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Link alerts</h1>
          <p className="text-sm text-muted">
            {canDecideAlerts(officer.role)
              ? "Open an alert to approve or reject it. Rejected alerts stay visible to every station."
              : "Every police role sees every alert, including rejected ones with the reason. Analysts and supervisors decide."}
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          {canScope && (
            <div className="flex gap-1 rounded-md border border-line p-0.5" role="group" aria-label="Which alerts">
              {(["station", "city"] as const).map((sc) => (
                <Link key={sc} href={href(tab, sort, sc)} aria-current={sc === scope ? "true" : undefined}
                  className={`rounded px-2 py-0.5 ${sc === scope ? "bg-signal-soft font-semibold text-signal" : "text-muted hover:text-ink"}`}>
                  {sc === "station" ? "My station" : "City-wide"}
                </Link>
              ))}
            </div>
          )}
          <div className="flex gap-1">
          {SORTS.map((s) => (
            <Link key={s} href={href(tab, s)} className={`rounded-md px-2 py-1 ${s === sort ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>
              {SORT_LABEL[s]}
            </Link>
          ))}
          </div>
        </div>
      </div>

      <nav className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-line" aria-label="Alert status">
        {TABS.map((t) => (
          <Link
            key={t} href={href(t, sort)} aria-current={t === tab ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${t === tab ? "border-signal font-semibold" : "border-transparent text-muted hover:text-ink"}`}
          >
            {TAB_LABEL[t]}
          </Link>
        ))}
      </nav>

      {error && <p role="alert" className="rounded-md border border-red-400 px-3 py-2 text-sm text-red-600">Could not load alerts: {error}</p>}
      {!error && alerts.length === 0 && (
        <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">
          No {TAB_LABEL[tab].toLowerCase()} alerts{scope === "station" && tab !== "mine" ? " involving your station" : ""}{tab === "mine" ? (officer.stationId ? " for your station" : " that you decided") : ""} yet.
          New alerts appear here live as the linking pipeline raises them.
        </p>
      )}
      <div className="grid gap-3 lg:grid-cols-2">
        {alerts.map((a) => <AlertCard key={a.alert_id} alert={a} crimes={crimes} deciderNames={deciderNames} />)}
      </div>
    </div>
  );
}
