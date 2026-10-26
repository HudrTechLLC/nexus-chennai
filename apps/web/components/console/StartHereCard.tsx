import Link from "next/link";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Officer } from "@/lib/auth";
import type { AlertRow } from "@/lib/overview";
import { HERO_ALERT_ID, HERO_SERIES_ID, heroSteps, startHereMode, stationPending, WHAT_NEXUS_DOES } from "@/lib/startHere";

/**
 * "Start here" (WS3-29) on console home. Analysts and up: what Nexus does, then three steps to the hero case.
 * Station officers: the pending link alerts on their station. View only: it links to the hero alert and
 * never decides it or reads more than its id.
 */
export async function StartHereCard({ sb, officer, alerts }: { sb: SupabaseClient; officer: Officer; alerts: AlertRow[] }) {
  if (startHereMode(officer.role) === "station") {
    const { rows, total } = stationPending(alerts, officer.stationId);
    return (
      <section className="rounded-xl border border-signal bg-surface p-5" aria-labelledby="start-here">
        <h2 id="start-here" className="font-semibold">Start here · your station&apos;s pending links</h2>
        {rows.length === 0 ? (
          <p className="mt-1 text-sm text-muted">
            No link alerts are waiting on {officer.stationId ?? "your station"}. When the agents link one of your cases to another
            station&apos;s, it appears here and in <Link href="/console/alerts" className="underline">Alerts</Link>.
          </p>
        ) : (
          <>
            <ul className="mt-2 divide-y divide-line text-sm">
              {rows.map((a) => (
                <li key={a.alert_id} className="flex flex-wrap items-baseline gap-3 py-1.5">
                  <Link href={`/console/alerts/${encodeURIComponent(a.alert_id)}`} className="font-mono text-xs underline-offset-2 hover:underline">{a.alert_id}</Link>
                  <span className="text-xs text-muted">{a.kind} · {(a.stations ?? []).map((s) => s.replace(/^PS-/, "")).join(" ↔ ")}</span>
                </li>
              ))}
            </ul>
            {total > rows.length && (
              <p className="mt-1 text-xs text-muted">
                {total - rows.length} more in <Link href="/console/alerts" className="underline">Alerts</Link>.
              </p>
            )}
          </>
        )}
      </section>
    );
  }

  const [alert, series] = await Promise.all([
    sb.from("link_alerts").select("alert_id").eq("alert_id", HERO_ALERT_ID).maybeSingle(),
    sb.from("series").select("series_id, name").eq("series_id", HERO_SERIES_ID).maybeSingle(),
  ]);
  const steps = heroSteps({
    heroAlert: (alert.data as { alert_id: string } | null) ?? null,
    heroSeries: (series.data as { series_id: string; name: string | null } | null) ?? null,
  });
  return (
    <section className="rounded-xl border border-signal bg-surface p-5" aria-labelledby="start-here">
      <h2 id="start-here" className="font-semibold">Start here</h2>
      <p className="mt-1 text-sm">{WHAT_NEXUS_DOES}</p>
      <ol className="mt-3 grid gap-3 md:grid-cols-3">
        {steps.map((s) => (
          <li key={s.n} className="rounded-lg border border-line p-3 text-sm">
            <div className="text-xs text-muted">Step {s.n}</div>
            <div className="font-medium">{s.title}</div>
            <p className="mt-1 text-xs text-muted">{s.body}</p>
            <Link href={s.href} className="mt-2 inline-block font-mono text-xs text-signal underline-offset-2 hover:underline">{s.cta} →</Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
