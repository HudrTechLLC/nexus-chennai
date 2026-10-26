import Link from "next/link";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Officer } from "@/lib/auth";
import type { AlertRow } from "@/lib/overview";
import { HERO_ALERT_ID, HERO_SERIES_ID, heroSteps, startHereKey, startHereMode, stationPending, WHAT_NEXUS_DOES } from "@/lib/startHere";
import { DismissibleStrip } from "./DismissibleStrip";

/** Station ids shown inline in the one-row strip; the rest fold into "N more in Alerts". */
const INLINE_ALERTS = 3;

/**
 * "Start here" (WS3-29) on console home: one compact, dismissible row below the KPI tiles.
 * Analysts and up: what Nexus does, then three linked steps to the hero case. Station officers: the pending
 * link alerts on their station. View only: it links to the hero alert and never decides it or reads more than its id.
 */
export async function StartHereCard({ sb, officer, alerts }: { sb: SupabaseClient; officer: Officer; alerts: AlertRow[] }) {
  const key = startHereKey(officer.userId);

  if (startHereMode(officer.role) === "station") {
    const { rows, total } = stationPending(alerts, officer.stationId, INLINE_ALERTS);
    const station = officer.stationId ? officer.stationId.replace(/^PS-/, "") : "your station";
    return (
      <DismissibleStrip storageKey={key}>
        <section aria-labelledby="start-here" className="flex items-center gap-x-4 overflow-hidden whitespace-nowrap text-sm">
          <h2 id="start-here" className="shrink-0 font-semibold">Start here</h2>
          {rows.length === 0 ? (
            <p className="min-w-0 truncate text-muted">
              No link alerts are waiting on {station}. New cross-station links to your cases appear here and in{" "}
              <Link href="/console/alerts" className="underline">Alerts</Link>.
            </p>
          ) : (
            <>
              <span className="shrink-0 text-muted">{total} pending on {station}:</span>
              <ul className="flex min-w-0 items-center gap-x-3 overflow-hidden">
                {rows.map((a) => (
                  <li key={a.alert_id} className="shrink-0">
                    <Link href={`/console/alerts/${encodeURIComponent(a.alert_id)}`} className="font-mono text-xs text-signal underline-offset-2 hover:underline"
                      title={`${a.kind} · ${(a.stations ?? []).map((s) => s.replace(/^PS-/, "")).join(" ↔ ")}`}>
                      {a.alert_id}
                    </Link>
                  </li>
                ))}
              </ul>
              {total > rows.length && (
                <Link href="/console/alerts" className="shrink-0 text-xs underline">{total - rows.length} more in Alerts</Link>
              )}
            </>
          )}
        </section>
      </DismissibleStrip>
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
    <DismissibleStrip storageKey={key}>
      <section aria-labelledby="start-here" className="flex items-center gap-x-4 overflow-hidden whitespace-nowrap text-sm">
        <h2 id="start-here" className="shrink-0 font-semibold">Start here</h2>
        <p className="min-w-0 truncate text-muted" title={WHAT_NEXUS_DOES}>{WHAT_NEXUS_DOES}</p>
        <ol className="flex shrink-0 items-center gap-x-3">
          {steps.map((s) => (
            <li key={s.n}>
              <Link href={s.href} title={s.body} className="text-signal underline-offset-2 hover:underline">
                <span className="text-muted">{s.n}.</span> {s.title} →
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </DismissibleStrip>
  );
}
