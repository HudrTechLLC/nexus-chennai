/**
 * "Start here" card on console home (WS3-29): a role-aware first step for a new viewer.
 * Analysts and up get one line on what Nexus does and three steps to the hero case; a station officer gets
 * the pending link alerts that touch their station. Pure helpers; the page passes rows it already read.
 */

import type { Role } from "@/lib/roles";
import type { AlertRow } from "@/lib/overview";

/** The hero case the demo walks through: the Red Pulsar Adyar <-> Velachery link and its series. */
export const HERO_ALERT_ID = "LA-2026-E38C6B38B865";
export const HERO_SERIES_ID = "SER-B687C36CFC";

export const WHAT_NEXUS_DOES =
  "Nexus reads every station's cases together, links crimes that look like the same offenders across " +
  "stations, and puts each link in front of an analyst with its evidence. A person decides; nothing is automatic.";

export type StartStep = { n: number; title: string; body: string; href: string; cta: string };

export function startHereMode(role: Role): "guide" | "station" {
  return role === "station_officer" ? "station" : "guide";
}

/**
 * The three steps to the hero case. Each step falls back to its list page when the hero row is missing
 * (another database, a re-run that changed ids), so the card never links to a 404.
 */
export function heroSteps(input: { heroAlert: { alert_id: string } | null; heroSeries: { series_id: string; name?: string | null } | null }): StartStep[] {
  const alert = input.heroAlert;
  const series = input.heroSeries;
  return [
    { n: 1, title: "Open the alert inbox", body: "Every cross-station link the agents raised, scored in code, with the Skeptic's check.",
      href: "/console/alerts", cta: "Alerts" },
    alert
      ? { n: 2, title: "Open the Red Pulsar alert", body: "Adyar and Velachery chain snatchings: factor bars, evidence rows with their Zetaris query ids, the vehicle trail.",
          href: `/console/alerts/${encodeURIComponent(alert.alert_id)}`, cta: alert.alert_id }
      : { n: 2, title: "Open the highest-scoring alert", body: "The demo alert is not in this database; sort the inbox by score and open the top one.",
          href: "/console/alerts", cta: "Alerts" },
    series
      ? { n: 3, title: "Read the series dossier", body: `${series.name || "The Red Pulsar series"}: member cases, map, timeline and the Markovian dossier.`,
          href: `/console/series/${encodeURIComponent(series.series_id)}`, cta: series.series_id }
      : { n: 3, title: "Read a series dossier", body: "The demo series is not in this database; open any series from the list.",
          href: "/console/series", cta: "Series" },
  ];
}

export const STATION_PENDING_LIMIT = 5;

/** Pending link alerts that touch the officer's station, newest first. */
export function stationPending(alerts: AlertRow[], stationId: string | null, limit = STATION_PENDING_LIMIT): { rows: AlertRow[]; total: number } {
  if (!stationId) return { rows: [], total: 0 };
  const mine = alerts
    .filter((a) => a.status === "pending" && (a.stations ?? []).includes(stationId))
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || a.alert_id.localeCompare(b.alert_id));
  return { rows: mine.slice(0, limit), total: mine.length };
}

/** Per-user localStorage key for a dismissed Start-here strip. */
export const startHereKey = (userId: string) => `nexus.startHere.dismissed.${userId}`;

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** True only when this user dismissed the strip. Missing or throwing storage (private mode) means shown. */
export function readDismissed(storage: StorageLike | null | undefined, key: string): boolean {
  try {
    return storage?.getItem(key) === "1";
  } catch {
    return false;
  }
}

/** Remember (or forget) a dismissal; storage errors are ignored, so the strip simply comes back next visit. */
export function writeDismissed(storage: StorageLike | null | undefined, key: string, dismissed: boolean): void {
  try {
    if (dismissed) storage?.setItem(key, "1");
    else storage?.removeItem(key);
  } catch {
    /* private mode or blocked storage: nothing to remember */
  }
}
