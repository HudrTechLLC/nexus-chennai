/**
 * Alert map (spec G2 /console/alerts/[alertId]: "map of both scenes + vehicle trail").
 * Pure helpers: distance and time between the two scenes, and the ANPR trail of the plates seen near them.
 */
import type { LonLat } from "@/lib/pulse";

/** A scene: the exact point and time where the officer may read the crime, else its H3 cell centre and ISO week. */
export type Scene = { id: string; p: LonLat; exact: boolean; at: string | null; week: string | null };

export type TrailRead = {
  read_id: string;
  camera_id: string;
  read_at: string;
  plate_text: string;
  crime_id: string | null;
  p: LonLat;
};

export type Gap = { km: number; approx: boolean; hours: number | null; weeks: number | null };

const RAD = Math.PI / 180;

/** Great-circle distance in km between two [lon, lat] points. */
export function haversineKm(a: LonLat, b: LonLat): number {
  const dLat = (b[1] - a[1]) * RAD;
  const dLon = (b[0] - a[0]) * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * RAD) * Math.cos(b[1] * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Monday 00:00 UTC of an ISO week label ("2026-W42"), or null. */
function isoWeekStart(label: string | null): number | null {
  const m = /^(\d{4})-W(\d{2})$/.exec(label ?? "");
  if (!m) return null;
  const jan4 = Date.UTC(Number(m[1]), 0, 4);
  const dow = new Date(jan4).getUTCDay() || 7;
  return jan4 - (dow - 1) * 86_400_000 + (Number(m[2]) - 1) * 7 * 86_400_000;
}

/** Distance and time between two scenes. Exact only when both are readable; otherwise cell centres and weeks. */
export function sceneGap(a: Scene | null, b: Scene | null): Gap | null {
  if (!a || !b) return null;
  const exact = a.exact && b.exact;
  const km = haversineKm(a.p, b.p);
  if (exact && a.at && b.at) {
    return { km, approx: false, hours: Math.abs(Date.parse(b.at) - Date.parse(a.at)) / 3_600_000, weeks: null };
  }
  const wa = isoWeekStart(a.week), wb = isoWeekStart(b.week);
  return { km, approx: !exact, hours: null, weeks: wa != null && wb != null ? Math.round(Math.abs(wb - wa) / (7 * 86_400_000)) : null };
}

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

/** "4.5 km apart · 2 days apart"; approximations say so. */
export function describeGap(g: Gap): string {
  const dist = g.approx ? `about ${g.km.toFixed(1)} km apart (area cells)` : `${g.km.toFixed(1)} km apart`;
  let time: string;
  if (g.hours != null) {
    const h = Math.round(g.hours);
    if (h < 1) time = "under 1 h apart";
    else if (h < 24) time = `${h} h apart`;
    else time = `${plural(Math.floor(h / 24), "day")}${h % 24 ? ` ${h % 24} h` : ""} apart`;
  } else if (g.weeks != null) {
    time = g.weeks === 0 ? "same ISO week" : `${plural(g.weeks, "week")} apart`;
  } else time = "time not visible to you";
  return `${dist} · ${time}`;
}

const normPlate = (s: string) => s.replace(/\s+/g, "").toUpperCase();

/**
 * The vehicle trail: every plate read near either scene (an ANPR read linked to one of the crimes), with all
 * reads of that plate in time order. One entry per plate.
 */
export function trailOf(reads: TrailRead[], crimeIds: string[]): { plate: string; reads: TrailRead[] }[] {
  const plates = new Set(reads.filter((r) => r.crime_id && crimeIds.includes(r.crime_id)).map((r) => normPlate(r.plate_text)));
  return Array.from(plates).sort().map((plate) => ({
    plate,
    reads: reads.filter((r) => normPlate(r.plate_text) === plate).sort((a, b) => a.read_at.localeCompare(b.read_at)),
  }));
}
