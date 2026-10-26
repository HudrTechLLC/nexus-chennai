import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { LinkAlert } from "@/lib/alerts";
import { crimeBriefs, type CrimeBrief } from "@/lib/alertsData";
import { chunk, type SeriesRow, type SeriesSummary } from "@/lib/series";
import type { MatrixPayload } from "@/lib/stationMatrix";
import type { TfStatus } from "@/lib/taskforces";

/** Server fetchers for the series and station pages. All reads run as the officer, under RLS. */

const PAGE = 1000; // PostgREST max-rows

/** Every series with city-wide member summaries (one RPC, no row cap). */
export async function fetchSeriesOverview(sb: SupabaseClient): Promise<{ rows: SeriesSummary[]; error: string | null }> {
  const { data, error } = await sb.rpc("series_overview");
  return { rows: ((data ?? []) as SeriesSummary[]), error: error?.message ?? null };
}

export async function fetchSeries(sb: SupabaseClient, seriesId: string): Promise<SeriesRow | null> {
  const { data } = await sb.from("series").select("*").eq("series_id", seriesId).maybeSingle();
  return (data as SeriesRow | null) ?? null;
}

/** Member crime ids, paging past the 1000-row cap. */
export async function fetchMemberIds(sb: SupabaseClient, seriesId: string): Promise<string[]> {
  const ids: string[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await sb.from("series_members").select("crime_id")
      .eq("series_id", seriesId).order("crime_id").range(from, from + PAGE - 1);
    if (error || !data) break;
    ids.push(...data.map((r) => r.crime_id as string));
    if (data.length < PAGE) break;
  }
  return ids;
}

/** crimeBriefs in chunks, so a series with hundreds of members never overflows the request URL. */
export async function briefsChunked(sb: SupabaseClient, ids: string[]): Promise<Record<string, CrimeBrief>> {
  const parts = await Promise.all(chunk(Array.from(new Set(ids)), 100).map((c) => crimeBriefs(sb, c)));
  return Object.assign({}, ...parts);
}

/** Link alerts that touch any member crime, newest first, de-duplicated across chunks. */
export async function alertsTouching(sb: SupabaseClient, ids: string[], limit = 200): Promise<LinkAlert[]> {
  const parts = await Promise.all(chunk(ids, 80).map(async (c) => {
    const { data } = await sb.from("link_alerts").select("alert_id, kind, crimes, stations, score, band, status, created_at, memory_applied, rationale")
      .overlaps("crimes", c).order("created_at", { ascending: false }).limit(limit);
    return (data ?? []) as LinkAlert[];
  }));
  const byId = new Map<string, LinkAlert>();
  for (const a of parts.flat()) byId.set(a.alert_id, a);
  return Array.from(byId.values()).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, limit);
}

export type TaskforceRow = { taskforce_id: string; name: string; status: TfStatus; created_at: string };

/** Joint task forces opened on this series. */
export async function taskforcesFor(sb: SupabaseClient, seriesId: string): Promise<TaskforceRow[]> {
  const { data } = await sb.from("taskforces").select("taskforce_id, name, status, created_at").eq("series_id", seriesId).neq("status", "declined").order("created_at", { ascending: false });
  return (data ?? []) as TaskforceRow[];
}

/** Station × station counts from link_alerts (one RPC). */
export async function fetchStationMatrix(sb: SupabaseClient, since: string | null): Promise<{ payload: MatrixPayload; error: string | null }> {
  const { data, error } = await sb.rpc("station_link_matrix", { p_since: since });
  const payload = (data ?? { cells: [], per_station: [], stations: [], alerts: 0 }) as MatrixPayload;
  return { payload, error: error?.message ?? null };
}
