import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { dayRange, plateIlike, plateMatches } from "@/lib/cases";
import { SEARCHABLE_TIP_STATUSES, evidenceFilter, personFilter, phoneRegex, type ParsedSearch } from "@/lib/search";
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
/** One ANPR camera read of a plate (map_anpr_reads; all police roles may read it). */
export type AnprHit = { read_id: string; camera_id: string; read_at: string; plate_text: string; plate_confidence: number | null; crime_id: string | null };
/** One evidence item (evidence_media, under can_read_crime). */
export type EvidenceHit = { evidence_id: string; crime_id: string; kind: string; camera_id: string | null; captured_at: string | null };

export type SearchResult = {
  /** True when a tag or linked facet matched more ids than one query carries, so results are a subset. */
  capped: boolean;
  cases: CaseRow[];
  vehicles: VehicleHit[];
  persons: PersonHit[];
  tips: TipHit[];
  anpr: AnprHit[];
  evidence: EvidenceHit[];
  sources: SourceUsed[];
};

const LIMIT = 50;
const ID_CAP = 500;

const intersect = (a: string[] | null, b: string[]) => (a === null ? b : a.filter((x) => b.includes(x)));
const CASE_COLS = "crime_id, station_id, fir_no, category, sub_type, occurred_from, reported_at, address, ward_no, severity, status";

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

  // Facets that narrow by id: MO/visual tag and time band (from the Extractor's features, city-wide
  // view), zone (stations), linked/unlinked (link_alerts). Each is reported as a source.
  const f = p.facets;
  let onlyIds: string[] | null = null;
  let capped = false;
  for (const tag of [f.mo, f.tod].filter((t): t is string => !!t)) {
    const { data, error } = await sb.from("crimes_citywide").select("crime_id").or(`mo_tags.ov.{"${tag}"},visual_tags.ov.{"${tag}"}`).limit(ID_CAP);
    const ids = (data ?? []).map((r) => r.crime_id as string);
    capped = capped || ids.length >= ID_CAP;
    onlyIds = intersect(onlyIds, ids);
    note(`Tag ${tag}`, "crimes_citywide (Extractor MO + visual tags)", ids.length, error?.message ?? null);
  }
  let zoneStations: string[] | null = null;
  if (f.zone) {
    const { data, error } = await sb.from("stations").select("station_id").eq("zone", f.zone);
    zoneStations = (data ?? []).map((r) => r.station_id as string);
    note(`Zone ${f.zone}`, "stations", zoneStations.length, error?.message ?? null);
  }
  let alertIds: string[] | null = null;
  if (f.linked) {
    const { data, error } = await sb.from("link_alerts").select("crimes").neq("status", "rejected").limit(1000);
    alertIds = Array.from(new Set((data ?? []).flatMap((a) => a.crimes as string[])));
    note("Linked", "link_alerts (pending + approved)", alertIds.length, error?.message ?? null);
    if (f.linked === "linked") onlyIds = intersect(onlyIds, alertIds.slice(0, ID_CAP));
  }

  // Cases.
  let cq = sb.from("crimes").select(CASE_COLS);
  if (f.station) cq = cq.eq("station_id", f.station);
  if (f.category) cq = cq.eq("category", f.category);
  if (f.status) cq = cq.eq("status", f.status);
  const { gte, lt } = dayRange(f.from, f.to);
  if (gte) cq = cq.gte("occurred_from", gte);
  if (lt) cq = cq.lt("occurred_from", lt);
  if (f.weapon) cq = cq.eq("weapon", f.weapon);
  if (zoneStations) cq = cq.in("station_id", zoneStations.length ? zoneStations : ["-"]);
  if (f.linked === "unlinked" && alertIds && alertIds.length) cq = cq.not("crime_id", "in", `(${alertIds.slice(0, ID_CAP).map((x) => `"${x}"`).join(",")})`);
  // A phone fragment: cases whose narrative or statements contain it, with or without spaces or dashes.
  if (p.kind === "phone") {
    const re = phoneRegex(p.value);
    const [byNarrative, byStatement] = await Promise.all([
      sb.from("crimes").select("crime_id").filter("narrative", "imatch", re).limit(ID_CAP),
      sb.from("statements").select("crime_id").filter("text", "imatch", re).limit(ID_CAP),
    ]);
    const ids = Array.from(new Set([...(byNarrative.data ?? []), ...(byStatement.data ?? [])].map((r) => r.crime_id as string)));
    capped = capped || ids.length >= ID_CAP;
    onlyIds = intersect(onlyIds, ids);
    note("Phone in narratives", "crimes.narrative", byNarrative.data?.length ?? 0, byNarrative.error?.message ?? null);
    note("Phone in statements", "statements.text", byStatement.data?.length ?? 0, byStatement.error?.message ?? null);
  }
  let skipCases = onlyIds !== null && onlyIds.length === 0;
  if (onlyIds && onlyIds.length) cq = cq.in("crime_id", onlyIds);
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
      sb.from("persons").select("person_id, name, aliases").or(personFilter(p.words)).limit(LIMIT),
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

  // ANPR camera reads: a plate fragment, matched the same way as vehicle plates (SRCH-01, SRCH-05).
  let anpr: AnprHit[] = [];
  if (p.kind === "plate") {
    const { data, error } = await sb.from("map_anpr_reads").select("read_id, camera_id, read_at, plate_text, plate_confidence, crime_id")
      .ilike("plate_text", plateIlike(p.value)).order("read_at", { ascending: false }).limit(200);
    anpr = ((data ?? []) as AnprHit[]).filter((r) => plateMatches(r.plate_text, p.value)).slice(0, LIMIT);
    note("ANPR reads", "map_anpr_reads", anpr.length, error?.message ?? null);
  }

  // Evidence: a camera id or an evidence kind word ("cctv", "photo"), or every item on one case.
  let evidence: EvidenceHit[] = [];
  if (p.kind === "crime_id" || (p.kind === "text" && p.words.length)) {
    let eq = sb.from("evidence_media").select("evidence_id, crime_id, kind, camera_id, captured_at");
    eq = p.kind === "crime_id" ? eq.eq("crime_id", p.value) : eq.or(evidenceFilter(p.words));
    const { data, error } = await eq.order("created_at", { ascending: false }).limit(LIMIT);
    evidence = (data ?? []) as EvidenceHit[];
    note("Evidence", "evidence_media", evidence.length, error?.message ?? null);
  }

  if (p.kind === "phone") {
    const { data, error } = await sb.from("tips").select("tip_id, category, text, received_week, status")
      .in("status", [...SEARCHABLE_TIP_STATUSES]).filter("text", "imatch", phoneRegex(p.value)).limit(LIMIT);
    tips = (data ?? []) as TipHit[];
    note("Tips", "tips (screened by Tip Guard only)", tips.length, error?.message ?? null);
  }

  return { capped, cases, vehicles, persons, tips, anpr, evidence, sources };
}
