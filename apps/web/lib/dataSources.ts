/**
 * Console "Data sources" page (WS3-27): every source Zetaris federates, what it is, what it feeds, and the
 * numbers the database actually has for it. Pure data and functions, so the page and the tests share them.
 *
 * Numbers are never written here. They come from Supabase at request time:
 *   - a row count of the Supabase table, or of its Supabase projection (map_* tables) where one exists;
 *   - per-source counts from system_status 'zetaris:sources' (written by app.dq_status, where Zetaris is
 *     reachable; Vercel cannot reach Zetaris, D-019), shown "as of <checked_at>, via Zetaris";
 *   - data-quality counts from system_status 'zetaris:dq'.
 * A source with none of these says "read live through Zetaris" instead of a number.
 *
 * Lineage ("feeds") follows zetaris/10_views.sql, 30_case.sql, 40_feeds.sql and the named queries in
 * services/api/app/adapters/zetaris_queries_n1.py. Nothing city-specific here (D-004).
 */

// =====================
// Types
// =====================

export type SourceType =
  | "Case records (Postgres)"
  | "Legacy FIR exports (files)"
  | "ANPR (files)"
  | "CCTV registry (files)"
  | "112 calls (files)"
  | "Offender records (files)"
  | "Reference data (files)"
  | "Open feeds (REST)";

export type DataSource = {
  /** The Zetaris name, e.g. "sb.crimes" or "s3csv.cctns". Also the key in 'zetaris:sources' counts. */
  id: string;
  label: string;
  type: SourceType;
  /** Where it physically lives, in plain words. */
  store: string;
  what: string;
  /** Unified views and agent queries it feeds. */
  feeds: string[];
  /** Supabase table that holds the rows, or a projection of them, for a count without Zetaris. */
  mirror?: { table: string; note?: string };
  /** True when its rows carry a police station, so it adds to the station-silo count. */
  stationScoped?: boolean;
  /** Keys of 'zetaris:dq' detail counted against this source. */
  dqRules?: string[];
};

// =====================
// Registry
// =====================

export const DATA_SOURCES: DataSource[] = [
  {
    id: "sb.crimes", label: "FIRs (current system)", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Every FIR filed in the current system, one row per crime, from each police station.",
    feeds: ["v_crime_unified", "case_bundle_v"], mirror: { table: "crimes" }, stationScoped: true,
  },
  {
    id: "sb.crime_vehicles", label: "Vehicles in cases", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Vehicles recorded against a crime: type, colour, partial plate.",
    feeds: ["case_bundle_v"], mirror: { table: "crime_vehicles" },
  },
  {
    id: "sb.statements", label: "Witness statements", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Statements taken for each case.",
    feeds: ["case_bundle_v", "q_news"], mirror: { table: "statements" },
  },
  {
    id: "sb.forensics", label: "Forensic results", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Forensic findings attached to cases.",
    feeds: ["case_bundle_v"], mirror: { table: "forensics" },
  },
  {
    id: "sb.crime_features_v", label: "Extracted case features", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "The method-of-operation features the agents extract from each FIR.",
    feeds: ["case_bundle_v", "q_features"], mirror: { table: "crime_features" },
  },
  {
    id: "sb.stations", label: "Police stations", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "The station registry: each station's name, zone and district.",
    feeds: ["v_crime_unified"], mirror: { table: "stations" },
  },
  {
    id: "sb.evidence_media", label: "Evidence", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Photos, CCTV stills and documents attached to cases, with chain of custody.",
    feeds: ["case_bundle_v"], mirror: { table: "evidence_media" }, dqRules: ["orphan_evidence"],
  },
  {
    id: "sb.tips_v", label: "Public tips", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "Anonymous tips from the public site (week and area only, never the sender).",
    feeds: ["q_tip_corroboration"], mirror: { table: "tips" }, dqRules: ["tip_without_incident"],
  },
  {
    id: "sb.section_map", label: "IPC to BNS sections", type: "Case records (Postgres)", store: "Supabase Postgres",
    what: "How old penal-code sections map to the new ones, so old and new FIRs compare.",
    feeds: ["v_crime_unified"], mirror: { table: "section_map" },
  },
  {
    id: "s3csv.cctns", label: "CCTNS export", type: "Legacy FIR exports (files)", store: "Zetaris file store (CSV)",
    what: "FIRs exported from the older CCTNS system, sections kept as raw text.",
    feeds: ["v_crime_unified"], stationScoped: true,
  },
  {
    id: "s3pq.archive", label: "FIR archive", type: "Legacy FIR exports (files)", store: "Zetaris file store (Parquet)",
    what: "Older FIRs from the station archives.",
    feeds: ["v_crime_unified"], stationScoped: true,
  },
  {
    id: "s3pq.anpr_reads", label: "ANPR plate reads", type: "ANPR (files)", store: "Zetaris file store (Parquet)",
    what: "Number-plate reads from road cameras: plate, time, direction.",
    feeds: ["q_vehicle_trail"], mirror: { table: "map_anpr_reads", note: "map projection: reads tied to cases" },
  },
  {
    id: "s3csv.anpr_cameras", label: "ANPR cameras", type: "ANPR (files)", store: "Zetaris file store (CSV)",
    what: "Where each number-plate camera is.", feeds: ["map layers"], mirror: { table: "map_anpr_cameras" },
  },
  {
    id: "s3csv.cctv_cameras", label: "CCTV registry", type: "CCTV registry (files)", store: "Zetaris file store (CSV)",
    what: "Public and private CCTV cameras, owner and contact station.",
    feeds: ["dq_stale_cameras", "map layers"], mirror: { table: "map_cctv_cameras" }, dqRules: ["stale_camera"],
  },
  {
    id: "s3pq.calls", label: "112 emergency calls", type: "112 calls (files)", store: "Zetaris file store (Parquet)",
    what: "Emergency calls by category and hour.",
    feeds: ["q_calls_near"], mirror: { table: "map_call_cells", note: "map projection: hexagon × category × hour cells, not calls" },
  },
  {
    id: "s3csv.releases", label: "Prison releases", type: "Offender records (files)", store: "Zetaris file store (CSV)",
    what: "Recent releases by ward, for the offender-return check.",
    feeds: ["q_offender_return"], mirror: { table: "map_release_density", note: "map projection: one row per ward" },
  },
  {
    id: "s3csv.history_sheets", label: "History sheets", type: "Offender records (files)", store: "Zetaris file store (CSV)",
    what: "Known offenders' recorded methods.", feeds: ["q_offender_return"],
  },
  {
    id: "s3csv.place_aliases", label: "Place names", type: "Reference data (files)", store: "Zetaris file store (CSV)",
    what: "Local names and spellings of places, tied to stations and wards, for matching news to crimes.",
    feeds: ["v_news_mentions", "q_news"],
  },
  {
    id: "s3csv.calendar", label: "Calendar", type: "Reference data (files)", store: "Zetaris file store (CSV)",
    what: "Festivals, holidays and events, for context on a case.", feeds: ["q_context"],
  },
  {
    id: "s3pq.osm_pois", label: "Points of interest", type: "Reference data (files)", store: "Zetaris file store (Parquet)",
    what: "Shops, transit stops and landmarks from OpenStreetMap, for context on a case.", feeds: ["q_context"],
  },
  {
    id: "nexus_feeds.rest_news", label: "Local news", type: "Open feeds (REST)", store: "REST feed (read by Zetaris)",
    what: "Local news articles, matched to crimes by place and time.", feeds: ["v_news_mentions", "q_news"],
  },
  {
    id: "nexus_feeds.rest_social", label: "Social posts", type: "Open feeds (REST)", store: "REST feed (read by Zetaris)",
    what: "Public posts about incidents.", feeds: ["social_posts (view; no agent reads it yet)"],
  },
  {
    id: "nexus_feeds.rest_weather", label: "Weather", type: "Open feeds (REST)", store: "REST feed (read by Zetaris)",
    what: "Hourly weather, for context on a case.", feeds: ["weather_hourly", "q_context"],
  },
];

export const SOURCE_TYPES: SourceType[] = Array.from(new Set(DATA_SOURCES.map((s) => s.type)));

// =====================
// Reading system_status rows
// =====================

export type StatusRow = { component: string; state: string; detail: unknown; checked_at: string | null };

const isCount = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;

/**
 * Per-source counts from 'zetaris:sources' (detail.counts: { "<source id>": n }). Unknown keys and
 * non-numbers are dropped; a missing or non-live row gives {} (the page then says "read live through Zetaris").
 */
export function zetarisCounts(row: StatusRow | undefined): Record<string, number> {
  // Only counts Zetaris itself produced: a sample-mode or failed run must never read as live.
  if (row?.state !== "live") return {};
  const counts = (row?.detail as { counts?: unknown } | null | undefined)?.counts;
  if (!counts || typeof counts !== "object") return {};
  const known = new Set(DATA_SOURCES.map((s) => s.id));
  return Object.fromEntries(Object.entries(counts as Record<string, unknown>).filter(([k, v]) => known.has(k) && isCount(v))) as Record<string, number>;
}

/** The DQ counts in 'zetaris:dq' that belong to one source, e.g. { duplicate_fir: 30 }. */
export function dqFor(source: DataSource, dqRow: StatusRow | undefined): Record<string, number> {
  const detail = (dqRow?.detail ?? {}) as Record<string, unknown>;
  return Object.fromEntries((source.dqRules ?? []).filter((r) => isCount(detail[r])).map((r) => [r, detail[r] as number]));
}

/**
 * Crime-level rules run over v_crime_unified, i.e. current FIRs and the legacy exports together
 * (zetaris/20_dq.sql), so they belong to the unified view, not to one source.
 */
export const UNIFIED_DQ_RULES = ["duplicate_fir", "bad_geo", "time_inconsistent", "unmapped_section"] as const;

/** The unified-view DQ counts in 'zetaris:dq', e.g. { duplicate_fir: 30, ... }. */
export function unifiedDq(dqRow: StatusRow | undefined): Record<string, number> {
  const detail = (dqRow?.detail ?? {}) as Record<string, unknown>;
  return Object.fromEntries(UNIFIED_DQ_RULES.filter((r) => isCount(detail[r])).map((r) => [r, detail[r] as number]));
}

/** Plain words for a DQ rule key. */
export const DQ_LABEL: Record<string, string> = {
  duplicate_fir: "possible duplicate FIRs",
  bad_geo: "missing or out-of-area locations",
  time_inconsistent: "inconsistent times",
  unmapped_section: "sections not mapped",
  orphan_evidence: "evidence without a crime",
  tip_without_incident: "tips not tied to an appeal",
  stale_camera: "camera records out of date",
};

// =====================
// What the page shows for one source
// =====================

export type SourceNumber =
  | { kind: "zetaris"; n: number; asOf: string | null }
  | { kind: "mirror"; n: number; table: string; note?: string }
  | { kind: "live-only" };

/**
 * The number for a source: the Zetaris count when 'zetaris:sources' has it (the whole source), else the
 * Supabase count of its table or projection, else nothing ("read live through Zetaris").
 */
export function sourceNumber(
  s: DataSource, zCounts: Record<string, number>, zAsOf: string | null, mirrorCounts: Record<string, number | null>,
): SourceNumber {
  if (isCount(zCounts[s.id])) return { kind: "zetaris", n: zCounts[s.id], asOf: zAsOf };
  const m = s.mirror && mirrorCounts[s.mirror.table];
  if (s.mirror && isCount(m)) return { kind: "mirror", n: m, table: s.mirror.table, note: s.mirror.note };
  return { kind: "live-only" };
}

/** Distinct Supabase tables the page counts. */
export const MIRROR_TABLES: string[] = Array.from(new Set(DATA_SOURCES.flatMap((s) => (s.mirror ? [s.mirror.table] : []))));
