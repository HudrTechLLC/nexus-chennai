import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Officer } from "@/lib/auth";
import type { LinkAlert, Scope, Tab } from "@/lib/alerts";

/** One crime as an alert card shows it. Full rows for crimes the officer may read, the city-wide summary otherwise. */
export type CrimeBrief = {
  crime_id: string;
  station_id: string;
  station_name: string;
  category: string;
  sub_type: string | null;
  fir_no: string | null; // null when only the city-wide summary is visible
  occurred_from: string | null;
  address: string | null;
  lat: number | null;
  lon: number | null;
  week: string | null;
  cell: string | null;
  mo_tags: string[];
  full: boolean;
};

const ALERT_SELECT = "*, link_factors(*), alert_decisions(*)";

/** Inbox rows for a tab. Every police role sees every status, including rejected (spec F4, Part I). */
export async function fetchInbox(sb: SupabaseClient, officer: Officer, tab: Tab, scope: Scope = "city", limit = 200): Promise<{ rows: LinkAlert[]; error: string | null }> {
  let q = sb.from("link_alerts").select(ALERT_SELECT).order("created_at", { ascending: false }).limit(limit);
  if (tab === "pending" || tab === "approved" || tab === "rejected") q = q.eq("status", tab);
  if (scope === "station" && officer.stationId) q = q.contains("stations", [officer.stationId]);
  if (tab === "mine") {
    if (officer.role === "station_officer" && officer.stationId) {
      q = q.contains("stations", [officer.stationId]);
    } else {
      const { data: mine, error } = await sb.from("alert_decisions").select("alert_id").eq("by", officer.userId).limit(500);
      if (error) return { rows: [], error: error.message };
      const ids = Array.from(new Set((mine ?? []).map((d) => d.alert_id as string)));
      if (ids.length === 0) return { rows: [], error: null };
      q = q.in("alert_id", ids);
    }
  }
  const { data, error } = await q;
  return { rows: (data ?? []) as LinkAlert[], error: error?.message ?? null };
}

export async function fetchAlert(sb: SupabaseClient, alertId: string): Promise<LinkAlert | null> {
  const { data } = await sb.from("link_alerts").select(ALERT_SELECT).eq("alert_id", alertId).maybeSingle();
  return (data as LinkAlert | null) ?? null;
}

/** Station names for display. */
export async function stationNames(sb: SupabaseClient, ids: string[]): Promise<Record<string, string>> {
  if (ids.length === 0) return {};
  const { data } = await sb.from("stations").select("station_id, name").in("station_id", Array.from(new Set(ids)));
  return Object.fromEntries((data ?? []).map((s) => [s.station_id, s.name]));
}

/** Briefs for the given crimes, respecting RLS: full rows where readable, city-wide summary for the rest. */
export async function crimeBriefs(sb: SupabaseClient, ids: string[]): Promise<Record<string, CrimeBrief>> {
  const uniq = Array.from(new Set(ids));
  if (uniq.length === 0) return {};
  const [{ data: full }, { data: summary }] = await Promise.all([
    sb.from("crimes").select("crime_id, station_id, category, sub_type, fir_no, occurred_from, address, lat, lon, week, h3_r8").in("crime_id", uniq),
    sb.from("crimes_citywide").select("crime_id, station_id, category, sub_type, cell, week, mo_tags").in("crime_id", uniq),
  ]);
  const names = await stationNames(sb, [...(full ?? []), ...(summary ?? [])].map((c) => c.station_id));
  const out: Record<string, CrimeBrief> = {};
  for (const s of summary ?? []) {
    out[s.crime_id] = {
      crime_id: s.crime_id, station_id: s.station_id, station_name: names[s.station_id] ?? s.station_id,
      category: s.category, sub_type: s.sub_type, fir_no: null, occurred_from: null, address: null, lat: null, lon: null,
      week: s.week, cell: s.cell, mo_tags: s.mo_tags ?? [], full: false,
    };
  }
  for (const c of full ?? []) {
    out[c.crime_id] = {
      ...(out[c.crime_id] ?? { mo_tags: [] }),
      crime_id: c.crime_id, station_id: c.station_id, station_name: names[c.station_id] ?? c.station_id,
      category: c.category, sub_type: c.sub_type, fir_no: c.fir_no, occurred_from: c.occurred_from, address: c.address,
      lat: c.lat, lon: c.lon, week: c.week, cell: c.h3_r8, full: true,
    };
  }
  return out;
}

/**
 * Names of the officers who decided alerts, readable by every police role (0004_01 officer_names).
 * Falls back to the profiles the caller can already read if the function is not deployed yet.
 */
export async function officerNames(sb: SupabaseClient, ids: string[]): Promise<Record<string, string>> {
  const uniq = Array.from(new Set(ids));
  if (uniq.length === 0) return {};
  const { data, error } = await sb.rpc("officer_names", { p_ids: uniq });
  if (!error) return Object.fromEntries(((data ?? []) as { user_id: string; name: string }[]).map((p) => [p.user_id, p.name]));
  const { data: rows } = await sb.from("profiles").select("user_id, name").in("user_id", uniq);
  return Object.fromEntries((rows ?? []).map((p) => [p.user_id, p.name]));
}

/** "Adyar 1182/2026", or the crime id when the FIR number is not visible to this officer. */
export function crimeTitle(c: CrimeBrief | undefined, id: string): string {
  if (!c) return id;
  const station = c.station_name.replace(/^PS-/, "");
  return c.fir_no ? `${station} ${c.fir_no}` : `${station} · ${id}`;
}

/** Case-file views and decisions are audited (spec J4). Failures never block the page. */
export async function audit(sb: SupabaseClient, what: string, objectType: string, objectId: string, details?: Record<string, unknown>) {
  await sb.from("audit_log").insert({ what, object_type: objectType, object_id: objectId, details: details ?? null });
}
