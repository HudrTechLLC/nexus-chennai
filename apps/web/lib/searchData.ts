import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { dayRange, plateIlike, plateMatches } from "@/lib/cases";
import { SEARCHABLE_TIP_STATUSES, type ParsedSearch } from "@/lib/search";
import type { CaseRow } from "@/lib/casesData";

/**
 * Runs a console search as the signed-in officer (RLS applies). Each group reports the source it
 * read, so the page can show "sources queried" (SRCH-07). The web console reads Supabase; agent
 * searches go through Zetaris named queries on the local pipeline.
 */

export type SourceUsed = { group: string; source: string; rows: number; error: string | null };
export type VehicleHit = { crime_id: string; plate_pattern: string | null; vehicle_type: string; make_model: string | null; colour: string | null; role: string };
export type PersonHit = { person_id: string; name: string | null; aliases: string[] };
export type TipHit = { tip_id: string; category: string; text: string; received_week: string; status: string };

export type SearchResult = {
  cases: CaseRow[];
  vehicles: VehicleHit[];
  persons: PersonHit[];
  tips: TipHit[];
  sources: SourceUsed[];
};

const LIMIT = 50;
const CASE_COLS = "crime_id, station_id, fir_no, category, sub_type, occurred_from, reported_at, address, severity, status";

export async function runSearch(sb: SupabaseClient, p: ParsedSearch): Promise<SearchResult> {
  const sources: SourceUsed[] = [];
  const note = (group: string, source: string, rows: number, error: string | null) => sources.push({ group, source, rows, error });

  // Vehicles first: a plate query narrows the cases to the crimes those vehicles belong to.
  let vehicles: VehicleHit[] = [];
  if (p.kind === "plate" || p.kind === "text") {
    let vq = sb.from("crime_vehicles").select("crime_id, plate_pattern, vehicle_type, make_model, colour, role").limit(200);
    if (p.kind === "plate") vq = vq.ilike("plate_pattern", plateIlike(p.value));
    else vq = vq.or(p.words.map((w) => `make_model.ilike.%${w}%,colour.ilike.%${w}%`).join(","));
    const { data, error } = await vq;
    vehicles = ((data ?? []) as VehicleHit[]).filter((v) => p.kind !== "plate" || plateMatches(v.plate_pattern, p.value));
    note("Vehicles", "crime_vehicles", vehicles.length, error?.message ?? null);
  }

  // Cases.
  let cq = sb.from("crimes").select(CASE_COLS);
  const f = p.facets;
  if (f.station) cq = cq.eq("station_id", f.station);
  if (f.category) cq = cq.eq("category", f.category);
  if (f.status) cq = cq.eq("status", f.status);
  const { gte, lt } = dayRange(f.from, f.to);
  if (gte) cq = cq.gte("occurred_from", gte);
  if (lt) cq = cq.lt("occurred_from", lt);
  let skipCases = false;
  if (p.kind === "crime_id") cq = cq.eq("crime_id", p.value);
  else if (p.kind === "fir") cq = p.value.includes("/") ? cq.eq("fir_no", p.value) : cq.like("fir_no", `${p.value}/%`);
  else if (p.kind === "plate") {
    const ids = Array.from(new Set(vehicles.map((v) => v.crime_id)));
    if (ids.length) cq = cq.in("crime_id", ids.slice(0, 200));
    else skipCases = true;
  } else if (p.kind === "text") {
    // Every word must appear in the narrative, address or sub-type (trigram index on narrative).
    for (const w of p.words) cq = cq.or(`narrative.ilike.%${w}%,address.ilike.%${w}%,sub_type.ilike.%${w}%`);
  }
  let cases: CaseRow[] = [];
  if (!skipCases) {
    const { data, error } = await cq.order("reported_at", { ascending: false }).limit(LIMIT);
    cases = (data ?? []) as CaseRow[];
    note("Cases", "crimes", cases.length, error?.message ?? null);
  } else note("Cases", "crimes", 0, null);

  // Persons and tips: words only.
  let persons: PersonHit[] = [];
  let tips: TipHit[] = [];
  if (p.kind === "text" && p.words.length) {
    const [pr, tr] = await Promise.all([
      sb.from("persons").select("person_id, name, aliases").or(p.words.map((w) => `name.ilike.%${w}%`).join(",")).limit(LIMIT),
      (() => {
        let tq = sb.from("tips").select("tip_id, category, text, received_week, status").in("status", [...SEARCHABLE_TIP_STATUSES]);
        for (const w of p.words) tq = tq.ilike("text", `%${w}%`);
        return tq.limit(LIMIT);
      })(),
    ]);
    persons = (pr.data ?? []) as PersonHit[];
    tips = (tr.data ?? []) as TipHit[];
    note("Persons", "persons", persons.length, pr.error?.message ?? null);
    note("Tips", "tips (screened by Tip Guard only)", tips.length, tr.error?.message ?? null);
  }

  return { cases, vehicles, persons, tips, sources };
}
