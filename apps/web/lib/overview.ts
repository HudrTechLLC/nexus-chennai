/**
 * Command overview (DASH-07, WS3-15): pure KPI, funnel, top-series and briefing helpers.
 * The page fetches rows under RLS and passes them in; nothing here reads or writes data.
 *
 * Definitions (chief, 26 Oct):
 *   open cases   = status registered or under_investigation. "Undetected" is a final status
 *                  (closed as untraced), so it is shown separately, never as open.
 *   this week    = the last 7 days, ending now.
 *   today        = since 00:00 IST.
 *   approval rate = approved / (approved + rejected); "—" when nothing is decided.
 */

export const IST_OFFSET_MIN = 330;
export const OPEN_STATUSES = ["registered", "under_investigation"] as const;

export type AlertRow = {
  alert_id: string;
  kind: string;
  stations: string[] | null;
  status: string;
  skeptic: { verdict?: string | null } | null;
  created_at: string;
};

/** 00:00 IST of the day containing `now`, as a Date. */
export function istMidnight(now: Date): Date {
  const shifted = new Date(now.getTime() + IST_OFFSET_MIN * 60_000);
  shifted.setUTCHours(0, 0, 0, 0);
  return new Date(shifted.getTime() - IST_OFFSET_MIN * 60_000);
}

export function weekAgo(now: Date): Date {
  return new Date(now.getTime() - 7 * 24 * 3600_000);
}

/** ISO-8601 week label ("2026-W44") of the IST calendar day containing `now`, as tips store it. */
export function istIsoWeek(now: Date): string {
  const d = new Date(now.getTime() + IST_OFFSET_MIN * 60_000);
  const day = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const dow = day.getUTCDay() || 7;
  day.setUTCDate(day.getUTCDate() + 4 - dow); // Thursday of this week decides the year
  const yearStart = new Date(Date.UTC(day.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((day.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7);
  return `${day.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

export const isCrossStation = (a: Pick<AlertRow, "stations">) => new Set(a.stations ?? []).size > 1;
const since = (iso: string, from: Date) => new Date(iso).getTime() >= from.getTime();

export type ApprovalRate = { approved: number; rejected: number; rate: number | null };

export function approvalRate(alerts: Pick<AlertRow, "status">[]): ApprovalRate {
  const approved = alerts.filter((a) => a.status === "approved").length;
  const rejected = alerts.filter((a) => a.status === "rejected").length;
  return { approved, rejected, rate: approved + rejected === 0 ? null : approved / (approved + rejected) };
}

/** raised → Skeptic-approved → analyst-approved, over the alerts passed in. */
export function alertFunnel(alerts: AlertRow[]): { raised: number; skepticApproved: number; analystApproved: number } {
  const skeptic = alerts.filter((a) => a.skeptic?.verdict === "approved");
  return {
    raised: alerts.length,
    skepticApproved: skeptic.length,
    analystApproved: skeptic.filter((a) => a.status === "approved").length,
  };
}

export function weekKpis(alerts: AlertRow[], now: Date): { newAlerts: number; crossStation: number } {
  const recent = alerts.filter((a) => since(a.created_at, weekAgo(now)));
  return { newAlerts: recent.length, crossStation: recent.filter(isCrossStation).length };
}

export type SeriesRow = { series_id: string; name: string; status: string; created_at: string | null };

/** Series with the most member cases first; closed series are left out. */
export function topSeries(series: SeriesRow[], members: { series_id: string }[], limit = 5): (SeriesRow & { members: number })[] {
  const n = new Map<string, number>();
  for (const m of members) n.set(m.series_id, (n.get(m.series_id) ?? 0) + 1);
  return series
    .filter((s) => s.status !== "closed")
    .map((s) => ({ ...s, members: n.get(s.series_id) ?? 0 }))
    .sort((a, b) => b.members - a.members || a.name.localeCompare(b.name))
    .slice(0, limit);
}

export type BriefingLine = { key: string; text: string; href: string; count: number };

export type BriefingInput = {
  alerts: AlertRow[];
  firsToday: number;
  tipsThisWeek: number;
  series: SeriesRow[];
  decisions: { at: string; decision: string }[];
  now: Date;
};

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "Today's briefing": one line per item, counted since 00:00 IST, generated from data (no LLM). */
export function briefing({ alerts, firsToday, tipsThisWeek, series, decisions, now }: BriefingInput): BriefingLine[] {
  const from = istMidnight(now);
  const newAlerts = alerts.filter((a) => since(a.created_at, from));
  const cross = newAlerts.filter(isCrossStation).length;
  const newSeries = series.filter((s) => s.created_at && since(s.created_at, from)).length;
  const today = decisions.filter((d) => since(d.at, from));
  const approved = today.filter((d) => d.decision === "approve").length;
  return [
    {
      key: "alerts", count: newAlerts.length, href: "/console/alerts",
      text: newAlerts.length === 0 ? "No new link alerts today." : `${plural(newAlerts.length, "new link alert")} today, ${cross} cross-station.`,
    },
    { key: "firs", count: firsToday, href: "/console/cases", text: firsToday === 0 ? "No FIRs registered today." : `${plural(firsToday, "FIR")} registered today.` },
    {
      key: "tips", count: tipsThisWeek, href: "/console/tips",
      text: `${tipsThisWeek === 0 ? "No tips" : plural(tipsThisWeek, "tip")} received this week (tips record only the week, to protect tipsters).`,
    },
    { key: "series", count: newSeries, href: "/console/series", text: newSeries === 0 ? "No new series today." : `${plural(newSeries, "new series", "new series")} today.` },
    {
      key: "decisions", count: today.length, href: "/console/alerts?tab=approved",
      text: today.length === 0 ? "No alert decisions today." : `${plural(today.length, "alert decision")} today: ${approved} approved, ${today.length - approved} rejected.`,
    },
  ];
}
