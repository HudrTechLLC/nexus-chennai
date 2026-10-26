import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { LinkAlert } from "@/lib/alerts";
import { dayRange, PAGE_SIZE, plateIlike, plateMatches, type CaseFilters } from "@/lib/cases";

/**
 * Case list and case file reads, always as the signed-in officer (RLS applies, D-003).
 * Station officers get full rows for their own station only; other stations come from
 * the city-wide summary view (Part I).
 */

// =====================
// Types
// =====================

export type CaseRow = {
  crime_id: string;
  station_id: string;
  fir_no: string;
  category: string;
  sub_type: string | null;
  occurred_from: string;
  reported_at: string;
  address: string | null;
  severity: number;
  status: string;
};

export type Crime = CaseRow & {
  sections: { code: string; ipc_equiv?: string | null }[];
  occurred_to: string | null;
  lat: number;
  lon: number;
  ward_no: number | null;
  h3_r8: string | null;
  week: string | null;
  property: Record<string, unknown>[];
  weapon: string | null;
  offenders_described: Record<string, unknown>[];
  victims: Record<string, unknown>[];
  narrative: string | null;
  synthetic: boolean;
  source: string;
};

export type CitywideCrime = {
  crime_id: string;
  station_id: string;
  category: string;
  sub_type: string | null;
  cell: string | null;
  week: string | null;
  mo_tags: string[] | null;
};

export type Features = {
  crime_id: string;
  extractor_version: string;
  mo: Record<string, unknown>;
  visual_tags: string[];
  entities: Record<string, unknown>;
  model: string;
  receipt_id: string | null;
  confidence: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export type Vehicle = { id: number; role: string; vehicle_type: string; plate_pattern: string | null; make_model: string | null; colour: string | null };
export type Statement = { statement_id: string; witness_ref: string; mode: "text" | "audio"; text: string | null; audio_path: string | null; transcript_model: string | null; recorded_at: string };
export type Evidence = { evidence_id: string; kind: string; storage_path: string; sha256: string; captured_at: string | null; camera_id: string | null; uploaded_by: string; vision: Record<string, unknown> | null; custody: unknown[]; created_at: string };
export type Diary = { entry_id: string; at: string; kind: string; text: string; author: string };
export type Forensic = { forensic_id: string; kind: string; match_code: string | null; reported_at: string | null };
export type PersonLink = { person_id: string; role: string; persons: { name: string | null; aliases: string[]; descriptors: Record<string, unknown> } | null };
export type SeriesRef = { series_id: string; name: string; status: string; added_at: string };
export type RunRef = { run_id: string; status: string; started: string };
export type TipLink = { tip_id: string; useful: boolean; at: string };
export type MoReview = { review_id: number; corrections: Record<string, unknown>; note: string | null; reviewed_by: string; reviewed_at: string };

export type CaseFile = {
  crime: Crime;
  features: Features | null;
  vehicles: Vehicle[];
  statements: Statement[];
  evidence: Evidence[];
  diary: Diary[];
  forensics: Forensic[];
  persons: PersonLink[];
  alerts: LinkAlert[];
  series: SeriesRef[];
  run: RunRef | null;
  reviews: MoReview[];
  tips: TipLink[];
};

const CASE_COLS = "crime_id, station_id, fir_no, category, sub_type, occurred_from, reported_at, address, severity, status";

// =====================
// Case list
// =====================

/** Most matching vehicles a plate filter reads; past this the list says it is capped. */
export const PLATE_CAP = 500;

/** Crime ids whose vehicles can match a plate fragment (RLS limits to readable crimes). */
export async function crimeIdsForPlate(sb: SupabaseClient, fragment: string, limit = PLATE_CAP): Promise<{ ids: string[]; capped: boolean }> {
  const { data } = await sb.from("crime_vehicles").select("crime_id, plate_pattern").ilike("plate_pattern", plateIlike(fragment)).limit(limit);
  const rows = data ?? [];
  return {
    ids: Array.from(new Set(rows.filter((v) => plateMatches(v.plate_pattern, fragment)).map((v) => v.crime_id as string))),
    capped: rows.length >= limit,
  };
}

/** One page of cases, newest report first, with the total for paging. */
export async function fetchCases(sb: SupabaseClient, f: CaseFilters): Promise<{ rows: CaseRow[]; total: number; error: string | null; capped?: boolean }> {
  let q = sb.from("crimes").select(CASE_COLS, { count: "exact" });
  let plateCapped = false;
  if (f.station) q = q.eq("station_id", f.station);
  if (f.category) q = q.eq("category", f.category);
  if (f.status) q = q.eq("status", f.status);
  const { gte, lt } = dayRange(f.from, f.to);
  if (gte) q = q.gte("occurred_from", gte);
  if (lt) q = q.lt("occurred_from", lt);
  if (f.fir) q = f.fir.includes("/") ? q.eq("fir_no", f.fir) : q.like("fir_no", `${f.fir}/%`);
  if (f.plate) {
    const hit = await crimeIdsForPlate(sb, f.plate);
    if (hit.ids.length === 0) return { rows: [], total: 0, error: null };
    plateCapped = hit.capped;
    q = q.in("crime_id", hit.ids);
  }
  const start = (f.page - 1) * PAGE_SIZE;
  const { data, count, error } = await q.order("reported_at", { ascending: false }).order("crime_id").range(start, start + PAGE_SIZE - 1);
  return { rows: (data ?? []) as CaseRow[], total: count ?? 0, error: error?.message ?? null, capped: plateCapped };
}

/** Stations for the filters and the FIR form. */
export async function stationOptions(sb: SupabaseClient): Promise<{ station_id: string; name: string; zone: string | null }[]> {
  const { data } = await sb.from("stations").select("station_id, name, zone").order("name");
  return (data ?? []) as { station_id: string; name: string; zone: string | null }[];
}

// =====================
// Case file
// =====================

/** The full case, or null when this officer may not read the full row (then try fetchCitywide). */
export async function fetchCaseFile(sb: SupabaseClient, crimeId: string): Promise<CaseFile | null> {
  const { data: crime } = await sb.from("crimes").select("*").eq("crime_id", crimeId).maybeSingle();
  if (!crime) return null;
  const [features, vehicles, statements, evidence, diary, forensics, persons, alerts, members, run] = await Promise.all([
    sb.from("crime_features").select("*").eq("crime_id", crimeId).maybeSingle(),
    sb.from("crime_vehicles").select("id, role, vehicle_type, plate_pattern, make_model, colour").eq("crime_id", crimeId).order("id"),
    sb.from("statements").select("statement_id, witness_ref, mode, text, audio_path, transcript_model, recorded_at").eq("crime_id", crimeId).order("recorded_at"),
    sb.from("evidence_media").select("evidence_id, kind, storage_path, sha256, captured_at, camera_id, uploaded_by, vision, custody, created_at").eq("crime_id", crimeId).order("created_at"),
    sb.from("case_diary").select("entry_id, at, kind, text, author").eq("crime_id", crimeId).order("at"),
    sb.from("forensics").select("forensic_id, kind, match_code, reported_at").eq("crime_id", crimeId),
    sb.from("person_links").select("person_id, role, persons(name, aliases, descriptors)").eq("crime_id", crimeId),
    sb.from("link_alerts").select("*, link_factors(*), alert_decisions(*)").contains("crimes", [crimeId]).order("created_at", { ascending: false }).limit(50),
    sb.from("series_members").select("series_id, added_at, series(name, status)").eq("crime_id", crimeId),
    latestRun(sb, crimeId),
  ]);
  const { data: tipLinks } = await sb.from("tip_reviews").select("tip_id, useful, at").eq("crime_id", crimeId).order("at", { ascending: false }).limit(50);
  const { data: reviews } = await sb.from("crime_feature_reviews").select("review_id, corrections, note, reviewed_by, reviewed_at")
    .eq("crime_id", crimeId).order("reviewed_at", { ascending: false }).limit(20);
  return {
    crime: crime as Crime,
    features: (features.data as Features | null) ?? null,
    vehicles: (vehicles.data ?? []) as Vehicle[],
    statements: (statements.data ?? []) as Statement[],
    evidence: (evidence.data ?? []) as Evidence[],
    diary: (diary.data ?? []) as Diary[],
    forensics: (forensics.data ?? []) as Forensic[],
    persons: (persons.data ?? []) as unknown as PersonLink[],
    alerts: (alerts.data ?? []) as LinkAlert[],
    series: ((members.data ?? []) as unknown as { series_id: string; added_at: string; series: { name: string; status: string } | null }[]).map((m) => ({
      series_id: m.series_id, added_at: m.added_at, name: m.series?.name ?? m.series_id, status: m.series?.status ?? "candidate",
    })),
    run,
    reviews: (reviews ?? []) as MoReview[],
    tips: (tipLinks ?? []) as TipLink[],
  };
}

/** City-wide summary of a case from another station (what a station officer may see). */
export async function fetchCitywide(sb: SupabaseClient, crimeId: string): Promise<CitywideCrime | null> {
  const { data } = await sb.from("crimes_citywide").select("crime_id, station_id, category, sub_type, cell, week, mo_tags").eq("crime_id", crimeId).maybeSingle();
  return (data as CitywideCrime | null) ?? null;
}

/**
 * Newest agent-graph run for this case (runs.subject = crime_id, migration 0006_03 by nexus-3).
 * Returns null until that column exists, so the page simply shows "processing".
 */
export async function latestRun(sb: SupabaseClient, crimeId: string): Promise<RunRef | null> {
  const { data, error } = await sb.from("runs").select("run_id, status, started").eq("subject", crimeId).order("started", { ascending: false }).limit(1).maybeSingle();
  if (error) return null;
  return (data as RunRef | null) ?? null;
}
