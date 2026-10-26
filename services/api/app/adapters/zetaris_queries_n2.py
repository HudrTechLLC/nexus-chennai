"""Named queries owned by the engines lane (nexus-2), merged into NAMED_QUERIES by adapters/zetaris.py.

Split agreed with nexus-1 (data lane), who owns adapters/zetaris.py and the core registry.
Each query is a dict of NamedQuery keyword arguments with a Lightning SQL form (Zetaris, schema `nexus`) and a DuckDB twin over the sample
bundle (data/sample/views.sql defines the same view names), and declares its output columns.

Lists come back as comma-joined strings in both forms (Spark `concat_ws(collect_list)`, DuckDB
`string_agg`), so the two return identical shapes.
"""

from __future__ import annotations

import functools


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

def slots(n: int) -> list[str]:
    """Parameter names id01..idNN for an IN list of n fixed slots."""
    return [f"id{i:02d}" for i in range(1, n + 1)]


def slot_params(ids, n: int) -> list[dict[str, str]]:
    """Parameter dicts for any number of ids: deduplicated, chunked by n, each chunk padded with '' (no id is '')."""
    uniq = list(dict.fromkeys(str(i) for i in ids if i))
    names = slots(n)
    return [{slot: (chunk[k] if k < len(chunk) else "") for k, slot in enumerate(names)}
            for chunk in (uniq[start:start + n] for start in range(0, len(uniq), n))]


DQ_IDS_PER_CALL = 50
DQ_IDS_MAX = 200  # more than this is not a plausible Planner request: refuse rather than run 5+ calls


def dq_flags_params(params: dict) -> list[dict]:
    """q_dq_flags live parameters: the comma-joined `ids` into :id01..:id50 slots, one dict per 50 ids. `ids`
    stays in every dict, so the files-mode SQL (and nothing else) can still bind it."""
    from .zetaris import ZetarisError

    ids = [i.strip() for i in str(params.get("ids") or "").split(",") if i.strip()]
    if len(dict.fromkeys(ids)) > DQ_IDS_MAX:
        raise ZetarisError(f"q_dq_flags: {len(dict.fromkeys(ids))} ids is more than {DQ_IDS_MAX}")
    batches = slot_params(ids, DQ_IDS_PER_CALL) or [{k: "" for k in slots(DQ_IDS_PER_CALL)}]
    return [{**params, **b} for b in batches]


# Data-quality flags (WS1-14) for a list of crimes. `ids` is a comma-joined string of crime ids
# (render() binds scalars only). Zetaris reads the nexus.dq_flags view from zetaris/20_dq.sql;
# the DuckDB twin applies the same rule text (adapters/dq_rules.py) inline.
def _dq_query() -> dict:
    from ..config import get_settings, load_city
    from . import dq_rules

    bounds = dq_rules.city_bounds(load_city(get_settings().city))
    return dict(
        name="q_dq_flags",
        # Live (0007_14): the snapshot app.dq_status writes after each full pass, filtered by a literal IN list that
        # Spark JDBC pushes down to Postgres (the PK leads with crime_id). The rule views cannot take the id filter
        # (sorted UNION + duplicate self-join, 55-80 s per call; PATH2 §3). computed_at is the extra last column
        # the client strips into the trace (as_of_column). other_id '' means "none" and comes back NULL as before.
        # One extra marker row (crime_id NULL) carries the snapshot time, so a clean answer (no flags) still says
        # which snapshot it was checked against; the client drops it (as_of_column).
        lightning=(
            "SELECT crime_id, rule, other_id, detail, computed_at FROM ("
            "SELECT crime_id, rule, NULLIF(other_id, '') AS other_id, detail, "
            "concat(CAST(computed_at AS STRING), ' UTC') AS computed_at FROM sb.dq_flags_snapshot "
            f"WHERE crime_id IN ({', '.join(':' + x for x in slots(DQ_IDS_PER_CALL))}) "
            "UNION ALL SELECT CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), "
            "concat(CAST(max(computed_at) AS STRING), ' UTC') FROM sb.dq_flags_snapshot"
            ") s ORDER BY crime_id, rule, other_id"  # ORDER BY: D-031; other_id is part of the key
        ),
        # Files mode (WS1-19) has no snapshot table: it keeps reading the rule views, as before.
        lightning_files=(
            "SELECT crime_id, rule, other_id, detail FROM nexus.dq_flags "
            "WHERE array_contains(split(:ids, ','), crime_id) ORDER BY crime_id, rule"
        ),
        expand=dq_flags_params,
        as_of_column=True,
        timeout_s=10.0,
        sample=(
            f"SELECT crime_id, rule, other_id, detail FROM ({dq_rules.flags_sql(dq_rules.DUCK, bounds)}) f "
            "WHERE list_contains(string_split(:ids, ','), crime_id)"
        ),
        description="Data-quality flags (duplicate FIR, bad geo, time inconsistent, unmapped section) for crimes",
        columns=dq_rules.COLUMNS,
    )


Q_DQ_FLAGS = _dq_query()


def _dq_all_query() -> dict:
    """Every crime-level flag, for the snapshot app.dq_status writes (0007_14). The full pass: 55-80 s live."""
    from ..config import get_settings, load_city
    from . import dq_rules

    bounds = dq_rules.city_bounds(load_city(get_settings().city))
    return dict(
        name="q_dq_flags_all",
        lightning="SELECT crime_id, rule, other_id, detail FROM nexus.dq_flags ORDER BY crime_id, rule, other_id",
        sample=(f"SELECT crime_id, rule, other_id, detail FROM ({dq_rules.flags_sql(dq_rules.DUCK, bounds)}) f "
                "ORDER BY crime_id, rule, other_id"),
        description="All data-quality flags (the snapshot app.dq_status writes for live q_dq_flags)",
        columns=dq_rules.COLUMNS, timeout_s=180.0,
    )


Q_DQ_FLAGS_ALL = _dq_all_query()

# NamedQuery keyword arguments; adapters/zetaris.py builds the NamedQuery objects (no import cycle).
N2_SPECS: dict[str, dict] = {q["name"]: q for q in (Q_HEX_COUNTS, Q_DQ_FLAGS, Q_DQ_FLAGS_ALL)}


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


@functools.lru_cache(maxsize=1)
def city_time() -> tuple[str, str]:
    """(timezone, "+HH:MM" offset) of the city pack (D-004).

    The offset comes from DuckDB's own timezone database (the twins already use it for AT TIME ZONE), not
    Python's zoneinfo, which needs the tzdata package on Windows: importing this module must never fail."""
    import duckdb

    from ..config import get_settings, load_city

    tz = load_city(get_settings().city)["timezone"]
    secs = duckdb.sql(
        "SELECT CAST(epoch(CAST(TIMESTAMPTZ '2026-01-01 00:00:00+00' AT TIME ZONE ? AS TIMESTAMP)) "
        "- epoch(TIMESTAMPTZ '2026-01-01 00:00:00+00') AS INTEGER)", params=[tz]).fetchone()[0]
    sign = "-" if secs < 0 else "+"
    return tz, f"{sign}{abs(secs) // 3600:02d}:{abs(secs) % 3600 // 60:02d}"


def _candidates_sample() -> str:
    """Same category, |calendar days| <= :days (UTC dates, as Spark datediff in a UTC session), haversine
    round(km, 3) <= :ring (R = 6371) after a bounding-box prefilter; ordered by km_apart, crime_id. occurred_from is
    returned as an ISO string in city time (timezone from the city pack, D-004)."""
    tz, offset = city_time()  # offset "+05:30": render() only binds ":<letter>...", so this is safe
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
NEWS_TIMEOUT_S = 12.0  # warm ~2 s; a cold first call ~9 s (2026-10-26), so 8 s tripped the breaker
NEWS_COLUMNS = ("crime_id", "article_id", "headline", "outlet", "published_at", "url", "matched_place",
                "hours_after", "category_hint")

Q_NEWS = dict(
    name="q_news",
    # The v_news_mentions logic (zetaris/40_feeds.sql #7), but the crime comes from sb.crimes for this one id.
    # v_crime_unified also unions the legacy CSV/parquet sources, where Zetaris cannot push the crime_id filter
    # down, so the view scanned them on every call (14-17 s live). q_news only ever runs for sb.crimes ids
    # (cases and q_candidates both read sb.crimes). Outer ORDER BY kept (D-031).
    lightning=(
        "SELECT c.crime_id, n.article_id, first(n.headline) AS headline, first(n.outlet) AS outlet, "
        "first(n.published_at) AS published_at, first(n.url) AS url, min(a.canonical) AS matched_place, "
        "CAST(floor((unix_timestamp(first(n.published_at)) - unix_timestamp(c.occurred_from)) / 3600) AS INT) "
        "AS hours_after, max(instr(lower(n.headline), split(c.category, '_')[0]) > 0) AS category_hint "
        "FROM (SELECT crime_id, station_id, ward_no, category, occurred_from FROM sb.crimes "
        "WHERE crime_id = :crime_id) c "
        "JOIN s3csv.place_aliases a ON (a.station_id = c.station_id OR a.ward_no = c.ward_no) "
        "JOIN (SELECT article_id, headline, outlet, published_at, url, place "
        "FROM nexus.news_items LATERAL VIEW explode(places_mentioned) p AS place) n "
        "ON lower(trim(n.place)) = lower(trim(a.alias)) "
        f"WHERE n.published_at >= c.occurred_from AND n.published_at < c.occurred_from + INTERVAL {NEWS_DAYS} DAYS "
        "GROUP BY c.crime_id, n.article_id, c.occurred_from ORDER BY published_at, article_id"
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
    # Zetaris reads the news REST table from this API (/mock-feeds), so a live q_news is a callback into us.
    # It is optional evidence: one attempt, 8 s, then skipped for the run; callers degrade to "no news".
    timeout_s=NEWS_TIMEOUT_S,
)
N2_SPECS[Q_NEWS["name"]] = Q_NEWS


# ---------------------------------------------------------------------------- q_search (spec E5, SRCH-02/03)
# Text plus structured filters over crimes and their witness statements. Zetaris returns the matching rows,
# newest first; app.engines.similarity.rank_rows re-ranks them by text relevance in code (D-027). Call it
# through search_params(q, filters), which fills every parameter: an empty string means "no filter".
#   pattern     word-prefix regex built from the query tokens ("" = no text filter)
#   category, station_id, status   exact match
#   since, until                    city-local dates or datetimes (ISO); until is exclusive
SEARCH_COLUMNS = ("crime_id", "station_id", "category", "sub_type", "occurred_from", "lat", "lon", "address",
                  "status", "severity", "text", "matched_in")
SEARCH_FILTERS = ("category", "station_id", "status", "since", "until")
SEARCH_MAX_TOKENS = 12


def search_pattern(q: str) -> str:
    """Word-prefix regex for the query: tokens are [a-z0-9] only, so nothing needs escaping, and there is no
    backslash (Spark SQL string literals would treat it as an escape)."""
    from app.engines.similarity import tokens

    toks = list(dict.fromkeys(tokens(q)))[:SEARCH_MAX_TOKENS]
    return f"(^|[^a-z0-9])({'|'.join(toks)})" if toks else ""


def search_params(q: str | None, filters: dict | None = None) -> dict[str, str]:
    """Every q_search parameter, from the search text and the console's filters."""
    f = filters or {}
    out = {"pattern": search_pattern(q or "")}
    for key in SEARCH_FILTERS:
        v = f.get(key)
        out[key] = "" if v is None else str(v)
    return out


def _city_tz() -> tuple[str, str]:
    return city_time()


def _q_search() -> dict:
    tz, offset = _city_tz()
    # Lightning (Spark SQL): sb.crimes timestamps arrive in UTC; city time via from_utc_timestamp (as q_case).
    ts = f"concat(replace(cast(from_utc_timestamp(c.occurred_from, '{tz}') AS STRING), ' ', 'T'), '{offset}')"
    hit = ("(lower(coalesce(c.narrative, '')) rlike :pattern OR lower(coalesce(c.address, '')) rlike :pattern "
           "OR lower(c.category) rlike :pattern)")
    lightning = (
        f"SELECT c.crime_id, c.station_id, c.category, c.sub_type, {ts} AS occurred_from, c.lat, c.lon, c.address, "
        f"c.status, c.severity, c.narrative AS text, "
        f"CASE WHEN :pattern = '' THEN 'filters' WHEN {hit} THEN 'crime' ELSE 'statement' END AS matched_in "
        "FROM sb.crimes c "
        "WHERE (:category = '' OR c.category = :category) AND (:station_id = '' OR c.station_id = :station_id) "
        "AND (:status = '' OR c.status = :status) "
        f"AND (:since = '' OR c.occurred_from >= to_utc_timestamp(CAST(:since AS TIMESTAMP), '{tz}')) "
        f"AND (:until = '' OR c.occurred_from < to_utc_timestamp(CAST(:until AS TIMESTAMP), '{tz}')) "
        f"AND (:pattern = '' OR {hit} OR c.crime_id IN (SELECT s.crime_id FROM sb.statements s "
        "WHERE lower(coalesce(s.text, '')) rlike :pattern)) "
        "ORDER BY c.occurred_from DESC, c.crime_id"
    )
    dhit = ("(regexp_matches(lower(coalesce(c.narrative, '')), :pattern) "
            "OR regexp_matches(lower(coalesce(c.address, '')), :pattern) "
            "OR regexp_matches(lower(c.category), :pattern))")
    sample = f"""
WITH c AS (SELECT *, CAST(occurred_from AS TIMESTAMPTZ) AS t FROM 'sb/crimes.parquet')
SELECT c.crime_id, c.station_id, c.category, c.sub_type,
       strftime(c.t AT TIME ZONE '{tz}', '%Y-%m-%dT%H:%M:%S') || '{offset}' AS occurred_from,
       c.lat, c.lon, c.address, c.status, c.severity, c.narrative AS text,
       CASE WHEN :pattern = '' THEN 'filters' WHEN {dhit} THEN 'crime' ELSE 'statement' END AS matched_in
FROM c
WHERE (:category = '' OR c.category = :category) AND (:station_id = '' OR c.station_id = :station_id)
  AND (:status = '' OR c.status = :status)
  AND (:since = '' OR c.t >= (CAST(:since AS TIMESTAMP) AT TIME ZONE '{tz}'))
  AND (:until = '' OR c.t < (CAST(:until AS TIMESTAMP) AT TIME ZONE '{tz}'))
  AND (:pattern = '' OR {dhit} OR c.crime_id IN (
        SELECT s.crime_id FROM 'sb/statements.parquet' s WHERE regexp_matches(lower(coalesce(s.text, '')), :pattern)))
ORDER BY c.t DESC, c.crime_id
""".strip()
    return dict(name="q_search", lightning=lightning, sample=sample, columns=SEARCH_COLUMNS,
                description="Text + filters over crimes and statements (SRCH-02/03); re-ranked in code")


Q_SEARCH = _q_search()
N2_SPECS[Q_SEARCH["name"]] = Q_SEARCH


# ---------------------------------------------------------------------------- q_station_matrix (spec E5)
# v_station_link_matrix: approved link alerts aggregated station x station, for the cross-station view and
# the "cross-station links this week" KPI (DASH-07). Every approved alert counts once for each unordered pair
# of distinct stations in it (station_a < station_b); an alert within one station counts on the diagonal.
#   since, until   city-local dates or datetimes on the alert's created_at ("" = open); until is exclusive
# link_alerts.stations is text[]: Postgres arrays arrive over JDBC as a '{a,b}' string, and the twin reads
# either that string or a list, so both forms strip brackets, quotes and spaces and split on commas.
MATRIX_COLUMNS = ("station_a", "station_b", "approved_links", "cross_station", "alert_ids")


def _q_station_matrix() -> dict:
    tz, _ = _city_tz()
    lightning = (
        "WITH a AS (SELECT alert_id, array_distinct(filter(split(regexp_replace(cast(stations AS STRING), "
        "'[{}\" ]', ''), ','), z -> z <> '')) AS st FROM sb.link_alerts WHERE status = 'approved' "
        f"AND (:since = '' OR created_at >= to_utc_timestamp(CAST(:since AS TIMESTAMP), '{tz}')) "
        f"AND (:until = '' OR created_at < to_utc_timestamp(CAST(:until AS TIMESTAMP), '{tz}'))), "
        "s AS (SELECT alert_id, size(st) AS n, e.s FROM a LATERAL VIEW explode(st) e AS s) "
        "SELECT x.s AS station_a, y.s AS station_b, count(DISTINCT x.alert_id) AS approved_links, "
        "x.s <> y.s AS cross_station, concat_ws(',', sort_array(collect_set(x.alert_id))) AS alert_ids "
        "FROM s x JOIN s y ON y.alert_id = x.alert_id AND (x.s < y.s OR (x.n = 1 AND x.s = y.s)) "
        "GROUP BY x.s, y.s ORDER BY approved_links DESC, station_a, station_b"
    )
    sample = f"""
WITH a AS (
  SELECT alert_id, CAST(created_at AS TIMESTAMPTZ) AS t,
         list_distinct(list_filter(string_split(regexp_replace(CAST(stations AS VARCHAR), '[]{{}}["'' ]', '', 'g'),
                                                ','), s -> s <> '')) AS st
  FROM 'sb/link_alerts.parquet' WHERE status = 'approved'),
w AS (SELECT * FROM a
      WHERE (:since = '' OR t >= (CAST(:since AS TIMESTAMP) AT TIME ZONE '{tz}'))
        AND (:until = '' OR t < (CAST(:until AS TIMESTAMP) AT TIME ZONE '{tz}'))),
s AS (SELECT alert_id, unnest(st) AS s, len(st) AS n FROM w),
p AS (SELECT x.alert_id, x.s AS station_a, y.s AS station_b FROM s x JOIN s y
      ON y.alert_id = x.alert_id AND (x.s < y.s OR (x.n = 1 AND x.s = y.s)))
SELECT station_a, station_b, count(DISTINCT alert_id) AS approved_links, station_a <> station_b AS cross_station,
       string_agg(DISTINCT alert_id, ',' ORDER BY alert_id) AS alert_ids
FROM p GROUP BY station_a, station_b ORDER BY approved_links DESC, station_a, station_b
""".strip()
    return dict(name="q_station_matrix", lightning=lightning, sample=sample, columns=MATRIX_COLUMNS,
                description="Approved link alerts aggregated station x station (v_station_link_matrix)")


Q_STATION_MATRIX = _q_station_matrix()
N2_SPECS[Q_STATION_MATRIX["name"]] = Q_STATION_MATRIX


# ---------------------------------------------------------------------------- q_context (spec E5 v_context)
# One row of context for a crime: city-local date, hour and day type; calendar entries that day (holidays,
# festivals, travel-heavy days, from s3csv.calendar); the POI types within POI_RADIUS_KM (s3pq.osm_pois);
# and the weather that hour (nexus.weather_hourly, Open-Meteo via zetaris/40_feeds.sql). The sample bundle
# has no weather export, so the twin returns null weather columns (agreed with nexus-1).
CONTEXT_COLUMNS = ("crime_id", "local_date", "hour_of_day", "day_type", "holidays", "holiday_kinds",
                   "travel_heavy", "poi_types", "pois_within", "nearest_poi_type", "nearest_poi_km",
                   "temperature_c", "precipitation_mm", "weather_code")
POI_RADIUS_KM = 0.5


def _km_sql(a: str, b: str) -> str:
    return (f"2 * 6371 * asin(sqrt(pow(sin(radians({b}.lat - {a}.lat) / 2), 2) + cos(radians({a}.lat)) * "
            f"cos(radians({b}.lat)) * pow(sin(radians({b}.lon - {a}.lon) / 2), 2)))")


def _q_context() -> dict:
    tz, _ = _city_tz()
    r = POI_RADIUS_KM
    box = (f"o.lat BETWEEN c.lat - {r} / 111.0 AND c.lat + {r} / 111.0 "
           f"AND o.lon BETWEEN c.lon - {r} / 108.0 AND c.lon + {r} / 108.0")
    lightning = (
        f"WITH c AS (SELECT crime_id, lat, lon, from_utc_timestamp(occurred_from, '{tz}') AS lt FROM sb.crimes "
        "WHERE crime_id = :crime_id), "
        f"p AS (SELECT o.poi_type, {_km_sql('c', 'o')} AS km FROM c JOIN s3pq.osm_pois o ON {box}), "
        "pa AS (SELECT concat_ws(',', sort_array(collect_set(poi_type))) AS poi_types, count(*) AS pois_within, "
        f"min_by(poi_type, km) AS nearest_poi_type, round(min(km), 3) AS nearest_poi_km FROM p WHERE km <= {r}), "
        "cal AS (SELECT k.date, concat_ws('; ', sort_array(collect_list(k.name))) AS holidays, "
        "concat_ws(',', sort_array(collect_set(k.kind))) AS holiday_kinds, "
        "max(lower(cast(k.travel_heavy AS STRING)) = 'true') AS travel_heavy "
        "FROM s3csv.calendar k GROUP BY k.date) "
        "SELECT c.crime_id, cast(to_date(c.lt) AS STRING) AS local_date, hour(c.lt) AS hour_of_day, "
        "CASE WHEN dayofweek(c.lt) IN (1, 7) THEN 'weekend' ELSE 'weekday' END AS day_type, "
        "cal.holidays, cal.holiday_kinds, coalesce(cal.travel_heavy, false) AS travel_heavy, "
        "pa.poi_types, pa.pois_within, pa.nearest_poi_type, pa.nearest_poi_km, "
        "w.temperature_c, w.precipitation_mm, w.weather_code "
        "FROM c CROSS JOIN pa "
        "LEFT JOIN cal ON cast(cal.date AS STRING) = cast(to_date(c.lt) AS STRING) "
        "LEFT JOIN nexus.weather_hourly w ON w.hour = replace(substring(cast(c.lt AS STRING), 1, 13), ' ', 'T')"
    )
    sample = f"""
WITH c AS (SELECT crime_id, lat, lon, CAST(occurred_from AS TIMESTAMPTZ) AT TIME ZONE '{tz}' AS lt
           FROM 'sb/crimes.parquet' WHERE crime_id = :crime_id),
p AS (SELECT o.poi_type, {_km_sql('c', 'o')} AS km FROM c JOIN 'ref/osm_pois.parquet' o ON {box}),
pa AS (SELECT string_agg(DISTINCT poi_type, ',' ORDER BY poi_type) AS poi_types, count(*) AS pois_within,
              arg_min(poi_type, km) AS nearest_poi_type, round(min(km), 3) AS nearest_poi_km
       FROM p WHERE km <= {r}),
cal AS (SELECT CAST(k.date AS VARCHAR) AS date, string_agg(k.name, '; ' ORDER BY k.name) AS holidays,
               string_agg(DISTINCT k.kind, ',' ORDER BY k.kind) AS holiday_kinds,
               bool_or(lower(CAST(k.travel_heavy AS VARCHAR)) = 'true') AS travel_heavy
        FROM read_csv_auto('ref/calendar.csv') k GROUP BY 1)
SELECT c.crime_id, CAST(CAST(c.lt AS DATE) AS VARCHAR) AS local_date, CAST(hour(c.lt) AS INTEGER) AS hour_of_day,
       CASE WHEN dayofweek(c.lt) IN (0, 6) THEN 'weekend' ELSE 'weekday' END AS day_type,
       cal.holidays, cal.holiday_kinds, coalesce(cal.travel_heavy, false) AS travel_heavy,
       pa.poi_types, pa.pois_within, pa.nearest_poi_type, pa.nearest_poi_km,
       CAST(NULL AS DOUBLE) AS temperature_c, CAST(NULL AS DOUBLE) AS precipitation_mm,
       CAST(NULL AS INTEGER) AS weather_code
FROM c CROSS JOIN pa LEFT JOIN cal ON cal.date = CAST(CAST(c.lt AS DATE) AS VARCHAR)
""".strip()
    return dict(name="q_context", lightning=lightning, sample=sample, columns=CONTEXT_COLUMNS,
                description="Calendar, nearby POI types and hourly weather for one crime (v_context)")


Q_CONTEXT = _q_context()
N2_SPECS[Q_CONTEXT["name"]] = Q_CONTEXT


# ---------------------------------------------------------------------------- q_cases (batch of q_case)
# The Planner fetches up to 25 candidates and the Skeptic re-reads pairs; each q_case is a Zetaris->Supabase
# trip (~1-3 s). q_cases reads the same contract for up to CASES_MAX ids in one trip: an IN list over
# sb.case_bundle_v, which Zetaris pushes down to Postgres (EXPLAIN: PushedFilters In(crime_id, [...])).
# render() binds scalars only, so the list is CASES_MAX fixed slots; cases_params() fills them ('' pads).
CASES_MAX = 25
_SLOTS = [f"id{i:02d}" for i in range(1, CASES_MAX + 1)]


def cases_params(ids) -> list[dict[str, str]]:
    """q_cases parameter dicts for any number of ids (deduplicated, chunked by CASES_MAX)."""
    return slot_params(ids, CASES_MAX)


def _q_cases() -> dict:
    from .case_bundle import q_case_lightning

    slots = ", ".join(f":{s}" for s in _SLOTS)
    one = q_case_lightning(CASE_COLUMNS)
    assert one.endswith("WHERE crime_id = :crime_id")
    lightning = one.replace("WHERE crime_id = :crime_id", f"WHERE crime_id IN ({slots}) ORDER BY crime_id")
    sample = (f"SELECT * FROM ({_CASE_SAMPLE.strip().replace('crime_id = :crime_id', f'crime_id IN ({slots})')}) q "
              "ORDER BY crime_id")
    return dict(name="q_cases", lightning=lightning, sample=sample, columns=CASE_COLUMNS,
                description="q_case for up to 25 crimes in one trip (Planner candidates, Skeptic pairs)")


Q_CASES = _q_cases()
N2_SPECS[Q_CASES["name"]] = Q_CASES
TWINS["q_cases"] = (Q_CASES["sample"], CASE_COLUMNS)


# ---------------------------------------------------------------------------- q_source_counts (WS3-27)
# Row count of every federated source, for the console Data sources page. Vercel cannot reach Zetaris
# (D-019), so app.dq_status runs this and writes system_status 'zetaris:sources' (detail.counts keyed by the
# source id). The ids are the page's registry ids (apps/web/lib/dataSources.ts; a test keeps them equal).
# A REST table is one JSON response per call, so the feeds are counted through their item views.
# The sample twin counts what the bundle has; a source the bundle lacks is NULL (not measured), never 0.
SOURCE_COUNT_COLUMNS = ("source", "n")
SOURCE_COUNTS: tuple[tuple[str, str, str | None], ...] = (
    # (registry id, relation counted live, DuckDB relation over data/sample or None)
    ("sb.crimes", "sb.crimes", "'sb/crimes.parquet'"),
    ("sb.crime_vehicles", "sb.crime_vehicles", "'sb/crime_vehicles.parquet'"),
    ("sb.statements", "sb.statements", "'sb/statements.parquet'"),
    ("sb.forensics", "sb.forensics", "'sb/forensics.parquet'"),
    ("sb.crime_features_v", "sb.crime_features_v", "'sb/crime_features.parquet'"),
    ("sb.stations", "sb.stations", "'sb/stations.parquet'"),
    ("sb.evidence_media", "sb.evidence_media", "'sb/evidence_media.parquet'"),
    ("sb.tips_v", "sb.tips_v", "'sb/tips.parquet'"),
    ("sb.section_map", "sb.section_map", "'sb/section_map.parquet'"),
    ("s3csv.cctns", "s3csv.cctns", "read_csv('legacy/cctns_*.csv', all_varchar = true, header = true)"),
    ("s3pq.archive", "s3pq.archive", "'legacy/archive.parquet'"),
    ("s3pq.anpr_reads", "s3pq.anpr_reads", "'anpr/reads.parquet'"),
    ("s3csv.anpr_cameras", "s3csv.anpr_cameras", None),
    ("s3csv.cctv_cameras", "s3csv.cctv_cameras", None),
    ("s3pq.calls", "s3pq.calls", "'calls/calls.parquet'"),
    ("s3csv.releases", "s3csv.releases", "read_csv('ref/releases.csv', all_varchar = true, header = true)"),
    ("s3csv.history_sheets", "s3csv.history_sheets", "read_csv('ref/history_sheets.csv', all_varchar = true, header = true)"),
    ("s3csv.place_aliases", "s3csv.place_aliases", "read_csv('ref/place_aliases.csv', all_varchar = true, header = true)"),
    ("s3csv.calendar", "s3csv.calendar", "read_csv('ref/calendar.csv', all_varchar = true, header = true)"),
    ("s3pq.osm_pois", "s3pq.osm_pois", "'ref/osm_pois.parquet'"),
    ("nexus_feeds.rest_news", "nexus.news_items", "read_json_auto('news/articles.jsonl')"),
    ("nexus_feeds.rest_social", "nexus.social_posts", "read_json_auto('social/posts.jsonl')"),
    ("nexus_feeds.rest_weather", "nexus.weather_hourly", None),
)


def _q_source_counts() -> dict:
    live = " UNION ALL ".join(f"SELECT '{sid}' AS source, count(*) AS n FROM {rel}" for sid, rel, _ in SOURCE_COUNTS)
    sample = " UNION ALL ".join(
        f"SELECT '{sid}' AS source, count(*) AS n FROM {rel}" if rel else f"SELECT '{sid}' AS source, CAST(NULL AS BIGINT) AS n"
        for sid, _, rel in SOURCE_COUNTS)
    return dict(name="q_source_counts", lightning=f"SELECT source, n FROM ({live}) s ORDER BY source",  # D-031
                sample=f"SELECT source, n FROM ({sample}) s ORDER BY source", columns=SOURCE_COUNT_COLUMNS,
                timeout_s=180.0, description="Row count of each federated source (Data sources page, via app.dq_status)")


Q_SOURCE_COUNTS = _q_source_counts()
N2_SPECS[Q_SOURCE_COUNTS["name"]] = Q_SOURCE_COUNTS
