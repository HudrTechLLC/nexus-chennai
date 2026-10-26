"""Named queries owned by the engines lane (nexus-2), merged into NAMED_QUERIES by adapters/zetaris.py.

Split agreed with nexus-1 (data lane), who owns adapters/zetaris.py and the core registry.
Each query is a dict of NamedQuery keyword arguments with a Lightning SQL form (Zetaris, schema `nexus`) and a DuckDB twin over the sample
bundle (data/sample/views.sql defines the same view names), and declares its output columns.

Lists come back as comma-joined strings in both forms (Spark `concat_ws(collect_list)`, DuckDB
`string_agg`), so the two return identical shapes.
"""

from __future__ import annotations


# Hotspot detector input (WS2-18): crimes per (h3_r9 cell, category, day) from baseline_since to until.
_HEX_COLUMNS = ("cell", "category", "day", "n", "crime_ids", "station_ids")

Q_HEX_COUNTS = dict(
    name="q_hex_counts",
    lightning=(
        "SELECT h3_r9 AS cell, category, CAST(occurred_from AS DATE) AS day, COUNT(*) AS n, "
        "concat_ws(',', collect_list(crime_id)) AS crime_ids, "
        "concat_ws(',', collect_set(station_id)) AS station_ids "
        "FROM nexus.v_crime_unified "
        "WHERE occurred_from >= CAST(:baseline_since AS TIMESTAMP) AND occurred_from < CAST(:until AS TIMESTAMP) "
        "AND h3_r9 IS NOT NULL "
        "GROUP BY h3_r9, category, CAST(occurred_from AS DATE)"
    ),
    sample=(
        "SELECT h3_r9 AS cell, category, CAST(occurred_from AS DATE) AS day, COUNT(*) AS n, "
        "string_agg(crime_id, ',' ORDER BY crime_id) AS crime_ids, "
        "string_agg(DISTINCT station_id, ',') AS station_ids "
        "FROM v_crime_unified "
        "WHERE occurred_from >= CAST(:baseline_since AS TIMESTAMP) AND occurred_from < CAST(:until AS TIMESTAMP) "
        "AND h3_r9 IS NOT NULL "
        "GROUP BY h3_r9, category, CAST(occurred_from AS DATE)"
    ),
    description="Crimes per h3_r9 cell, category and day over the baseline + window (Hotspot detector)",
    columns=_HEX_COLUMNS,
)

# Data-quality flags (WS1-14) for a list of crimes. `ids` is a comma-joined string of crime ids
# (render() binds scalars only). Zetaris reads the nexus.dq_flags view from zetaris/20_dq.sql;
# the DuckDB twin applies the same rule text (adapters/dq_rules.py) inline.
def _dq_query() -> dict:
    from ..config import get_settings, load_city
    from . import dq_rules

    bounds = dq_rules.city_bounds(load_city(get_settings().city))
    return dict(
        name="q_dq_flags",
        lightning=(
            "SELECT crime_id, rule, other_id, detail FROM nexus.dq_flags "
            "WHERE array_contains(split(:ids, ','), crime_id)"
        ),
        sample=(
            f"SELECT crime_id, rule, other_id, detail FROM ({dq_rules.flags_sql(dq_rules.DUCK, bounds)}) f "
            "WHERE list_contains(string_split(:ids, ','), crime_id)"
        ),
        description="Data-quality flags (duplicate FIR, bad geo, time inconsistent, unmapped section) for crimes",
        columns=dq_rules.COLUMNS,
    )


Q_DQ_FLAGS = _dq_query()

# NamedQuery keyword arguments; adapters/zetaris.py builds the NamedQuery objects (no import cycle).
N2_SPECS: dict[str, dict] = {q["name"]: q for q in (Q_HEX_COUNTS, Q_DQ_FLAGS)}


# ------------------------------------------------------------------------------------------------
# DuckDB twins for nexus-1's crime-side named queries (offered to shorten the data critical path).
# nexus-1 writes the Lightning SQL in the core registry and combines it with these `sample` forms
# into one NamedQuery; a parity test checks the column names. Contracts come from nexus-1.
# Inputs: data/sample/sb/<table>.parquet with Supabase column names; jsonb columns are JSON strings.
# Note: render() binds `:name`, so every other colon in this SQL is followed by a space.
# ------------------------------------------------------------------------------------------------

CASE_COLUMNS = (
    "crime_id", "source", "source_row_id", "station_id", "fir_no", "category", "sub_type", "sections",
    "occurred_from", "occurred_to", "reported_at", "lat", "lon", "address", "ward_no", "h3_r9", "h3_r8",
    "geohash7", "week", "severity", "property", "weapon", "offenders_described", "victims", "status",
    "narrative", "synthetic", "vehicles", "statements", "evidence", "forensics", "features",
)

_CASE_SAMPLE = """
WITH c AS (SELECT * FROM 'sb/crimes.parquet' WHERE crime_id = :crime_id),
veh AS (
  SELECT crime_id, CAST(to_json(list({'role': role, 'type': vehicle_type, 'plate': plate_pattern,
         'make_model': make_model, 'colour': colour} ORDER BY role, vehicle_type, coalesce(plate_pattern, ''),
         coalesce(make_model, ''))) AS VARCHAR) AS vehicles
  FROM 'sb/crime_vehicles.parquet' WHERE crime_id = :crime_id GROUP BY crime_id),
st AS (
  SELECT crime_id, CAST(to_json(list({'statement_id': statement_id, 'witness_ref': witness_ref, 'mode': mode,
         'text': "text", 'recorded_at': CAST(recorded_at AS VARCHAR)} ORDER BY statement_id)) AS VARCHAR) AS statements
  FROM 'sb/statements.parquet' WHERE crime_id = :crime_id GROUP BY crime_id),
ev AS (
  SELECT crime_id, CAST(to_json(list({'evidence_id': evidence_id, 'kind': kind, 'storage_path': storage_path,
         'captured_at': CAST(captured_at AS VARCHAR), 'camera_id': camera_id, 'vision': json(vision)}
         ORDER BY evidence_id)) AS VARCHAR) AS evidence
  FROM 'sb/evidence_media.parquet' WHERE crime_id = :crime_id GROUP BY crime_id),
fo AS (
  SELECT crime_id, CAST(to_json(list({'forensic_id': forensic_id, 'kind': kind, 'match_code': match_code}
         ORDER BY forensic_id)) AS VARCHAR) AS forensics
  FROM 'sb/forensics.parquet' WHERE crime_id = :crime_id GROUP BY crime_id),
f AS (
  SELECT crime_id, CAST(to_json({'crime_id': crime_id, 'extractor_version': extractor_version,
         'mo': json(mo), 'visual_tags': visual_tags, 'entities': json(entities), 'model': model,
         'receipt_id': receipt_id, 'confidence': confidence, 'reviewed_by': reviewed_by}) AS VARCHAR) AS features
  FROM 'sb/crime_features.parquet' WHERE crime_id = :crime_id)
SELECT c.crime_id, c.source, c.source_row_id, c.station_id, c.fir_no, c.category, c.sub_type, c.sections,
       c.occurred_from, c.occurred_to, c.reported_at, c.lat, c.lon, c.address, c.ward_no, c.h3_r9, c.h3_r8,
       c.geohash7, c.week, c.severity, c.property, c.weapon, c.offenders_described, c.victims, c.status,
       c.narrative, c.synthetic,
       coalesce(veh.vehicles, '[]') AS vehicles, coalesce(st.statements, '[]') AS statements,
       coalesce(ev.evidence, '[]') AS evidence, coalesce(fo.forensics, '[]') AS forensics, f.features
FROM c LEFT JOIN veh USING (crime_id) LEFT JOIN st USING (crime_id) LEFT JOIN ev USING (crime_id)
       LEFT JOIN fo USING (crime_id) LEFT JOIN f USING (crime_id)
""".strip()

FEATURES_COLUMNS = ("crime_id", "extractor_version", "model", "receipt_id", "mo", "visual_tags", "entities",
                    "confidence", "reviewed_by_officer")

_FEATURES_SAMPLE = """
SELECT crime_id, extractor_version, model, receipt_id, mo, CAST(to_json(visual_tags) AS VARCHAR) AS visual_tags,
       entities, confidence, reviewed_by IS NOT NULL AS reviewed_by_officer
FROM 'sb/crime_features.parquet'
WHERE list_contains(string_split(:ids, ','), crime_id)
ORDER BY crime_id
""".strip()

CANDIDATES_COLUMNS = ("crime_id", "station_id", "category", "sub_type", "occurred_from", "lat", "lon", "h3_r9",
                      "geohash7", "days_apart", "km_apart", "same_station")


def _candidates_sample() -> str:
    """Same category, |calendar days| <= :days (UTC dates, as Spark datediff in a UTC session), haversine
    round(km, 3) <= :ring (R = 6371) after a bounding-box prefilter; ordered by km_apart, crime_id. occurred_from is
    returned as an ISO string in city time (timezone from the city pack, D-004)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from ..config import get_settings, load_city

    tz = load_city(get_settings().city)["timezone"]
    off = datetime(2026, 1, 1, tzinfo=ZoneInfo(tz)).strftime("%z")
    offset = f"{off[:3]}:{off[3:]}"  # "+05:30" (render() only binds ":<letter>...", so this is safe)
    utc_day = "CAST(CAST({x} AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS DATE)"
    return f"""
WITH c AS (SELECT * FROM 'sb/crimes.parquet'),
a AS (SELECT * FROM c WHERE crime_id = :crime_id),
p AS (
  SELECT b.*,
         date_diff('day', {utc_day.format(x='a.occurred_from')}, {utc_day.format(x='b.occurred_from')}) AS signed_days,
         2 * 6371 * asin(sqrt(pow(sin(radians(b.lat - a.lat) / 2), 2)
             + cos(radians(a.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - a.lon) / 2), 2))) AS km,
         b.station_id = a.station_id AS same_st
  FROM a JOIN c b ON b.category = a.category AND b.crime_id <> a.crime_id
  WHERE abs(b.lat - a.lat) <= :ring / 111.0
    AND abs(b.lon - a.lon) <= :ring / (111.0 * cos(radians(a.lat))))
SELECT crime_id, station_id, category, sub_type,
       strftime(CAST(occurred_from AS TIMESTAMPTZ) AT TIME ZONE '{tz}', '%Y-%m-%dT%H:%M:%S')
         || '{offset}' AS occurred_from,
       lat, lon, h3_r9, geohash7, CAST(abs(signed_days) AS INTEGER) AS days_apart, round(km, 3) AS km_apart,
       same_st AS same_station
FROM p WHERE abs(signed_days) <= :days AND round(km, 3) <= :ring  -- the Lightning form filters on the rounded km_apart
ORDER BY km_apart, crime_id
""".strip()


# name -> (DuckDB sample SQL, output columns)
TWINS: dict[str, tuple[str, tuple[str, ...]]] = {
    "q_case": (_CASE_SAMPLE, CASE_COLUMNS),
    "q_features": (_FEATURES_SAMPLE, FEATURES_COLUMNS),
    "q_candidates": (_candidates_sample(), CANDIDATES_COLUMNS),
}


# News mentions for a crime (WS1-16). An article mentions a crime when one of its places_mentioned is an
# alias (cities/<city>/place_aliases.csv -> ref/place_aliases.csv) of the crime's station or ward, and it
# was published within NEWS_DAYS days after the crime. category_hint = the headline names the category's
# first word (e.g. "chain" for chain_snatching); it is reported, not required. One row per article.
NEWS_DAYS = 4
NEWS_COLUMNS = ("crime_id", "article_id", "headline", "outlet", "published_at", "url", "matched_place",
                "hours_after", "category_hint")

Q_NEWS = dict(
    name="q_news",
    lightning=(
        "SELECT crime_id, article_id, headline, outlet, published_at, url, matched_place, hours_after, category_hint "
        "FROM nexus.v_news_mentions WHERE crime_id = :crime_id ORDER BY published_at, article_id"
    ),
    sample=f"""
WITH c AS (
  SELECT crime_id, station_id, ward_no, category, CAST(occurred_from AS TIMESTAMPTZ) AS occurred_from
  FROM 'sb/crimes.parquet' WHERE crime_id = :crime_id),
n AS (
  SELECT article_id, headline, outlet, CAST(published_at AS TIMESTAMPTZ) AS published_at, url,
         unnest(places_mentioned) AS place
  FROM read_json_auto('news/articles.jsonl') WHERE synthetic),
a AS (SELECT alias, canonical, station_id, ward_no FROM read_csv_auto('ref/place_aliases.csv'))
SELECT c.crime_id, n.article_id, any_value(n.headline) AS headline, any_value(n.outlet) AS outlet,
       CAST(any_value(n.published_at) AS VARCHAR) AS published_at, any_value(n.url) AS url,
       min(a.canonical) AS matched_place,
       CAST(floor(epoch(any_value(n.published_at) - c.occurred_from) / 3600) AS INTEGER) AS hours_after,
       bool_or(contains(lower(n.headline), split_part(c.category, '_', 1))) AS category_hint
FROM c JOIN a ON (a.station_id = c.station_id OR a.ward_no = c.ward_no)
       JOIN n ON lower(trim(n.place)) = lower(trim(a.alias))
WHERE n.published_at >= c.occurred_from AND n.published_at < c.occurred_from + INTERVAL {NEWS_DAYS} DAY
GROUP BY c.crime_id, n.article_id, c.occurred_from
ORDER BY any_value(n.published_at), n.article_id
""".strip(),
    description="News articles that mention a crime's place within a few days of it",
    columns=NEWS_COLUMNS,
)
N2_SPECS[Q_NEWS["name"]] = Q_NEWS
