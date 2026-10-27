"""Named queries owned by the data lane (nexus-1), merged into NAMED_QUERIES by adapters/zetaris.py.

Lightning SQL runs on Zetaris against the registered sources (sb.* = Supabase via the read-only
role; nexus.* = semantic views once 10_views.sql lands). The DuckDB twin (sample mode) comes from
nexus-2's TWINS when present, so both forms declare the same output columns.

Output conventions (shared with the twins):
- timestamps are ISO 8601 strings in city time, e.g. 2026-10-14T19:40:00+05:30
- jsonb columns arrive as JSON strings; nested lists are JSON strings ("[]" when empty)
- list parameters are comma-joined strings (render() binds scalars only)
"""

from __future__ import annotations

from typing import Any

from ..config import REPO_ROOT, get_settings, load_city


def _city_time() -> tuple[str, str]:
    """(IANA zone, UTC offset) from the city pack; nothing city-specific in code (D-004)."""
    import yaml

    city = get_settings().city
    tz = load_city(city)["timezone"]
    gen = REPO_ROOT / "cities" / city / "generator" / "config.yaml"
    offset = yaml.safe_load(gen.read_text(encoding="utf-8"))["utc_offset"] if gen.is_file() else "+00:00"
    return tz, offset


def _ts(col: str, tz: str, offset: str) -> str:
    # cast-to-string keeps ':' out of the SQL text (render() treats ':name' as a parameter)
    return f"concat(replace(cast(from_utc_timestamp({col}, '{tz}') AS STRING), ' ', 'T'), '{offset}')"


CASE_COLUMNS = (
    "crime_id", "source", "source_row_id", "station_id", "fir_no", "category", "sub_type", "sections",
    "occurred_from", "occurred_to", "reported_at", "lat", "lon", "address", "ward_no", "h3_r9", "h3_r8",
    "geohash7", "week", "severity", "property", "weapon", "offenders_described", "victims", "status",
    "narrative", "synthetic", "vehicles", "statements", "evidence", "forensics", "features",
)
CANDIDATE_COLUMNS = ("crime_id", "station_id", "category", "sub_type", "occurred_from", "lat", "lon", "h3_r9",
                     "geohash7", "days_apart", "km_apart", "same_station")
FEATURES_COLUMNS = ("crime_id", "extractor_version", "model", "receipt_id", "mo", "visual_tags", "entities",
                    "confidence", "reviewed_by_officer")


def _q_case_bundle() -> str:
    """q_case reads sb.case_bundle_v (zetaris/30_case.sql, nexus-2): the same columns pre-joined in Postgres, so
    a call is one JDBC trip instead of six (live median 3.2 s vs 20.4 s, identical rows on 6 crimes). The
    six-scan form below is kept as the reference for what the view reproduces."""
    from .case_bundle import q_case_lightning

    return q_case_lightning(CASE_COLUMNS)


def _q_case(tz: str, off: str) -> str:
    t = lambda c: _ts(c, tz, off)  # noqa: E731
    return (
        "SELECT c.crime_id, c.source, c.source_row_id, c.station_id, c.fir_no, c.category, c.sub_type, c.sections, "
        f"{t('c.occurred_from')} AS occurred_from, {t('c.occurred_to')} AS occurred_to, "
        f"{t('c.reported_at')} AS reported_at, c.lat, c.lon, c.address, c.ward_no, c.h3_r9, c.h3_r8, c.geohash7, "
        "c.week, c.severity, c.property, c.weapon, c.offenders_described, c.victims, c.status, c.narrative, "
        "c.synthetic, coalesce(v.vehicles, '[]') AS vehicles, coalesce(s.statements, '[]') AS statements, "
        "coalesce(e.evidence, '[]') AS evidence, coalesce(f.forensics, '[]') AS forensics, cf.features "
        "FROM sb.crimes c "
        "LEFT JOIN (SELECT crime_id, to_json(collect_list(named_struct('role', role, 'type', vehicle_type, "
        "'plate', plate_pattern, 'make_model', make_model, 'colour', colour))) AS vehicles "
        "FROM sb.crime_vehicles WHERE crime_id = :crime_id GROUP BY crime_id) v ON v.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('statement_id', statement_id, "
        f"'witness_ref', witness_ref, 'mode', mode, 'text', text, 'recorded_at', {t('recorded_at')})))) AS statements "
        "FROM sb.statements WHERE crime_id = :crime_id GROUP BY crime_id) s ON s.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('evidence_id', evidence_id, "
        f"'kind', kind, 'storage_path', storage_path, 'captured_at', {t('captured_at')}, 'camera_id', camera_id, "
        "'vision', vision)))) AS evidence FROM sb.evidence_media WHERE crime_id = :crime_id GROUP BY crime_id) e "
        "ON e.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(sort_array(collect_list(named_struct('forensic_id', forensic_id, "
        "'kind', kind, 'match_code', match_code)))) AS forensics FROM sb.forensics WHERE crime_id = :crime_id "
        "GROUP BY crime_id) f ON f.crime_id = c.crime_id "
        "LEFT JOIN (SELECT crime_id, to_json(named_struct('extractor_version', extractor_version, 'model', model, "
        "'receipt_id', receipt_id, 'mo', mo, 'visual_tags', visual_tags, 'entities', entities, 'confidence', confidence, "
        "'reviewed_by_officer', reviewed_by_officer)) AS features FROM sb.crime_features_v "
        "WHERE crime_id = :crime_id) cf ON cf.crime_id = c.crime_id "
        "WHERE c.crime_id = :crime_id"
    )


Q_FEATURES = (
    "SELECT crime_id, extractor_version, model, receipt_id, mo, visual_tags, entities, confidence, "
    "reviewed_by_officer FROM sb.crime_features_v "
    "WHERE array_contains(split(:ids, ','), crime_id) ORDER BY crime_id"  # ORDER BY: D-031, see zetaris.py
)


def _km(a: str, b: str) -> str:
    """Haversine distance in km between two aliases' lat/lon (Spark SQL)."""
    return (f"2 * 6371 * asin(sqrt(pow(sin(radians({b}.lat - {a}.lat) / 2), 2) + cos(radians({a}.lat)) * "
            f"cos(radians({b}.lat)) * pow(sin(radians({b}.lon - {a}.lon) / 2), 2)))")


def _q_candidates(tz: str, off: str) -> str:
    """Blocking (spec F1 step 3): same category, within :days, within :ring km of the crime.

    The lat/lon box prefilter keeps the self-join small; the exact ring uses haversine."""
    return (
        "SELECT crime_id, station_id, category, sub_type, occurred_from, lat, lon, h3_r9, geohash7, days_apart, "
        "km_apart, same_station FROM (SELECT b.crime_id, b.station_id, b.category, b.sub_type, "
        f"{_ts('b.occurred_from', tz, off)} AS occurred_from, b.lat, b.lon, b.h3_r9, b.geohash7, "
        "abs(datediff(b.occurred_from, a.occurred_from)) AS days_apart, "
        f"round({_km('a', 'b')}, 3) AS km_apart, b.station_id = a.station_id AS same_station "
        "FROM sb.crimes a JOIN sb.crimes b ON b.category = a.category AND b.crime_id <> a.crime_id "
        "WHERE a.crime_id = :crime_id AND abs(datediff(b.occurred_from, a.occurred_from)) <= :days "
        "AND b.lat BETWEEN a.lat - :ring / 111.0 AND a.lat + :ring / 111.0 "
        "AND b.lon BETWEEN a.lon - :ring / 108.0 AND a.lon + :ring / 108.0) t "
        "WHERE km_apart <= :ring ORDER BY km_apart, crime_id"
    )


TIP_COLUMNS = ("tip_id", "crime_id", "received_week", "summary", "tags", "verdict", "status", "category",
               "channel", "approx_cell")
_TIP_STATUSES = "('screened', 'reviewed', 'urgent')"  # never unscreened ('new') or quarantined tips (R8)


def _q_tip_corroboration(tz: str) -> str:
    """Screened tips in the crime's H3 r8 cell, received from the crime's ISO week to :days after it.
    Tips are untrusted: only Tip Guard's vocabulary-only summary and tags leave Zetaris, never text."""
    day = f"date_add(CAST(from_utc_timestamp(c.occurred_from, '{tz}') AS DATE), :days)"
    week_end = (f"concat(CAST(extract(YEAROFWEEK FROM {day}) AS STRING), '-W', "
                f"lpad(CAST(weekofyear({day}) AS STRING), 2, '0'))")
    return (
        "SELECT t.tip_id, c.crime_id, t.received_week, get_json_object(t.guard, '$.summary') AS summary, "
        "coalesce(get_json_object(t.guard, '$.tags'), '[]') AS tags, get_json_object(t.guard, '$.verdict') AS verdict, "
        "t.status, t.category, t.channel, t.approx_cell "
        "FROM sb.crimes c JOIN sb.tips_v t ON t.approx_cell = c.h3_r8 "
        f"WHERE c.crime_id = :crime_id AND t.status IN {_TIP_STATUSES} "
        f"AND t.received_week >= c.week AND t.received_week <= {week_end} "
        "ORDER BY t.received_week, t.tip_id"
    )


def _q_tip_corroboration_sample(tz: str) -> str:
    day = f"CAST(timezone('{tz}', c.occurred_from) AS DATE) + CAST(:days AS INTEGER)"
    return (
        "SELECT t.tip_id, c.crime_id, t.received_week, json_extract_string(t.guard, '$.summary') AS summary, "
        "coalesce(CAST(json_extract(t.guard, '$.tags') AS VARCHAR), '[]') AS tags, "
        "json_extract_string(t.guard, '$.verdict') AS verdict, t.status, t.category, t.channel, t.approx_cell "
        "FROM 'sb/crimes.parquet' c JOIN 'sb/tips.parquet' t ON t.approx_cell = c.h3_r8 "
        f"WHERE c.crime_id = :crime_id AND t.status IN {_TIP_STATUSES} "
        f"AND t.received_week >= c.week AND t.received_week <= strftime({day}, '%G-W%V') "
        "ORDER BY t.received_week, t.tip_id"
    )


TRAIL_COLUMNS = ("read_id", "camera_id", "read_at", "plate_text", "plate_confidence", "direction", "lat", "lon",
                 "h3_r9", "crime_id", "km_from_scene", "minutes_from_scene")
SCENE_KM, SCENE_MINUTES = 1.5, 120  # a read is "near a scene" within this distance and time of a crime


def _q_vehicle_trail(tz: str, off: str, *, sample: bool) -> str:
    """ANPR reads of a plate (pattern: '?' = any one character, spaces ignored) from :pad_days before
    min(:t0, :t1) to :pad_days after max(:t0, :t1). Each read carries the nearest crime scene within
    SCENE_KM / SCENE_MINUTES (crime_id, else null), which is what the vehicle factor scores on."""
    if sample:
        reads, crimes = "'anpr/reads.parquet'", "'sb/crimes.parquet'"
        pat = "replace(upper(regexp_replace(:plate_pattern, '[^A-Za-z0-9?]', '', 'g')), '?', '_')"
        ts = lambda x: f"CAST({x} AS TIMESTAMPTZ)"  # noqa: E731
        lo, hi = f"least({ts(':t0')}, {ts(':t1')})", f"greatest({ts(':t0')}, {ts(':t1')})"
        win = lambda e, sign, d: f"{e} {sign} to_days(CAST({d} AS INTEGER))"  # noqa: E731
        secs = lambda x: f"epoch({x})"  # noqa: E731
        out_ts = (f"strftime(r.read_at AT TIME ZONE '{tz}', '%Y-%m-%dT%H:%M:%S') || '{off}'")
    else:
        reads, crimes = "s3pq.anpr_reads", "sb.crimes"
        pat = "replace(upper(regexp_replace(:plate_pattern, '[^A-Za-z0-9?]', '')), '?', '_')"
        ts = lambda x: f"CAST({x} AS TIMESTAMP)"  # noqa: E731
        lo, hi = f"least({ts(':t0')}, {ts(':t1')})", f"greatest({ts(':t0')}, {ts(':t1')})"
        win = lambda e, sign, d: f"{e} {sign} make_interval(0, 0, 0, CAST({d} AS INT), 0, 0, 0)"  # noqa: E731
        secs = lambda x: f"unix_timestamp({x})"  # noqa: E731
        out_ts = _ts("r.read_at", tz, off)
    deg = SCENE_KM / 108.0
    km = ("2 * 6371 * asin(sqrt(pow(sin(radians(s.lat - r.lat) / 2), 2) + cos(radians(r.lat)) * cos(radians(s.lat)) "
          "* pow(sin(radians(s.lon - r.lon) / 2), 2)))")
    return (
        f"WITH r AS (SELECT read_id, camera_id, read_at, plate_text, plate_confidence, direction, lat, lon, h3_r9 "
        f"FROM {reads} WHERE plate_text LIKE {pat} "
        f"AND read_at BETWEEN {win(lo, '-', ':pad_days')} AND {win(hi, '+', ':pad_days')}), "
        f"s AS (SELECT crime_id, occurred_from, lat, lon FROM {crimes} "
        f"WHERE occurred_from BETWEEN {win(lo, '-', ':pad_days + 1')} AND {win(hi, '+', ':pad_days + 1')}), "
        f"j AS (SELECT r.read_id, s.crime_id, {km} AS km, "
        f"abs({secs('r.read_at')} - {secs('s.occurred_from')}) / 60.0 AS mins FROM r JOIN s "
        f"ON abs(s.lat - r.lat) <= {deg:.6f} AND abs(s.lon - r.lon) <= {deg:.6f} "
        f"AND abs({secs('r.read_at')} - {secs('s.occurred_from')}) <= {SCENE_MINUTES * 60}), "
        f"n AS (SELECT read_id, crime_id, km, mins, row_number() OVER (PARTITION BY read_id ORDER BY km, crime_id) AS k "
        f"FROM j WHERE km <= {SCENE_KM}) "
        f"SELECT r.read_id, r.camera_id, {out_ts} AS read_at, r.plate_text, r.plate_confidence, r.direction, r.lat, "
        f"r.lon, r.h3_r9, n.crime_id, round(n.km, 3) AS km_from_scene, CAST(round(n.mins) AS INT) AS minutes_from_scene "
        f"FROM r LEFT JOIN n ON n.read_id = r.read_id AND n.k = 1 ORDER BY r.read_at, r.read_id"
    )


RETURN_COLUMNS = ("person_ref", "release_id", "released_on", "release_type", "residence_ward", "near_home",
                  "prior_mo_tags", "matched_tags", "mo_overlap", "days_since_release", "sheet_id", "sheet_category",
                  "sheet_active")
RETURN_DAYS = 60  # spec D2: an offender's MO reappears within 60 days of release


def _q_offender_return(tz: str, *, sample: bool) -> str:
    """Offenders released within RETURN_DAYS before :since whose prior MO shares a tag with :mo_tags
    (comma-joined), days counted on the city's calendar. City-wide, ranked: home ward (= :ward) first, then MO overlap, then most recent.
    mo_overlap = shared tags / prior tags (0-1), the value the offender_return factor reads."""
    if sample:
        rel, hs = "'ref/releases.csv'", "'ref/history_sheets.csv'"
        split = "string_split({x}, '{sep}')"
        inter, size = "list_intersect({a}, {b})", "len({x})"
        days = f"date_diff('day', CAST(r.released_on AS DATE), CAST(timezone('{tz}', CAST(:since AS TIMESTAMPTZ)) AS DATE))"
        join = "array_to_string({x}, ',')"
    else:
        rel, hs = "s3csv.releases", "s3csv.history_sheets"
        split = "split({x}, '{sep}')"
        inter, size = "array_intersect({a}, {b})", "size({x})"
        days = f"datediff(CAST(from_utc_timestamp(CAST(:since AS TIMESTAMP), '{tz}') AS DATE), CAST(r.released_on AS DATE))"
        join = "concat_ws(',', {x})"
    prior = split.format(x="r.prior_mo_tags", sep=";")
    asked = split.format(x=":mo_tags", sep=",")
    shared = inter.format(a=prior, b=asked)
    return (
        "SELECT person_ref, release_id, released_on, release_type, residence_ward, near_home, prior_mo_tags, "
        "matched_tags, mo_overlap, days_since_release, sheet_id, sheet_category, sheet_active FROM ("
        "SELECT r.person_ref, r.release_id, CAST(CAST(r.released_on AS DATE) AS VARCHAR(10)) AS released_on, "
        "r.release_type, CAST(r.residence_ward AS INT) AS residence_ward, "
        "CAST(r.residence_ward AS INT) = CAST(:ward AS INT) AS near_home, r.prior_mo_tags, "
        f"{join.format(x=shared)} AS matched_tags, "
        f"round({size.format(x=shared)} / CAST({size.format(x=prior)} AS DOUBLE), 3) AS mo_overlap, "
        f"{days} AS days_since_release, h.sheet_id, h.category AS sheet_category, h.active AS sheet_active "
        f"FROM {rel} r LEFT JOIN {hs} h ON h.person_ref = r.person_ref) t "
        f"WHERE days_since_release BETWEEN 0 AND {RETURN_DAYS} AND mo_overlap > 0 "
        "ORDER BY near_home DESC, mo_overlap DESC, released_on DESC, person_ref LIMIT 50"
    )


CALLS_COLUMNS = ("call_id", "crime_id", "received_at", "category", "lat", "lon", "cell", "dispatched_unit",
                 "outcome", "fir_ref", "km_from_scene", "minutes_from_start")


def _q_calls_near(tz: str, off: str, *, sample: bool) -> str:
    """112 calls within :km of a crime, received from :minutes before it started to :minutes after it
    ended (defaults 1 km, 120 min). minutes_from_start is signed (negative = before the crime)."""
    if sample:
        calls, crimes = "'calls/calls.parquet'", "'sb/crimes.parquet'"
        secs = lambda x: f"epoch({x})"  # noqa: E731
        out_ts = f"strftime(k.received_at AT TIME ZONE '{tz}', '%Y-%m-%dT%H:%M:%S') || '{off}'"
    else:
        calls, crimes = "s3pq.calls", "sb.crimes"
        secs = lambda x: f"unix_timestamp({x})"  # noqa: E731
        out_ts = _ts("k.received_at", tz, off)
    km = ("2 * 6371 * asin(sqrt(pow(sin(radians(k.lat - c.lat) / 2), 2) + cos(radians(c.lat)) * cos(radians(k.lat)) "
          "* pow(sin(radians(k.lon - c.lon) / 2), 2)))")
    start, end = secs("c.occurred_from"), secs("coalesce(c.occurred_to, c.occurred_from)")
    return (
        "SELECT call_id, crime_id, received_at, category, lat, lon, cell, dispatched_unit, outcome, fir_ref, "
        "km_from_scene, minutes_from_start FROM ("
        f"SELECT k.call_id, c.crime_id, {out_ts} AS received_at, k.category, k.lat, k.lon, k.cell, k.dispatched_unit, "
        f"k.outcome, k.fir_ref, round({km}, 3) AS km_from_scene, "
        f"CAST(round(({secs('k.received_at')} - {start}) / 60.0) AS INT) AS minutes_from_start "
        f"FROM {crimes} c JOIN {calls} k ON abs(k.lat - c.lat) <= :km / 108.0 AND abs(k.lon - c.lon) <= :km / 108.0 "
        f"AND {secs('k.received_at')} BETWEEN {start} - :minutes * 60 AND {end} + :minutes * 60 "
        "WHERE c.crime_id = :crime_id) t WHERE km_from_scene <= :km ORDER BY minutes_from_start, call_id"
    )


def _twin(name: str, columns: tuple[str, ...]) -> str:
    """The DuckDB twin from nexus-2 when available; otherwise a stub that fails the width check loudly."""
    try:
        from .zetaris_queries_n2 import TWINS  # type: ignore[attr-defined]
    except ImportError:
        TWINS = {}
    sample, cols = TWINS.get(name, (None, None))
    if sample is None:
        return "SELECT 'no sample twin yet' AS note"
    if tuple(cols) != columns:
        raise ValueError(f"{name}: twin columns {cols} differ from the contract {columns}")
    return sample


# Data-quality counts for /console/system (D-029: Vercel cannot reach Zetaris, so app.dq_status writes them to
# system_status). One row per rule view in zetaris/20_dq.sql (dq_flags is the union of the first four).
DQ_SUMMARY_COLUMNS = ("rule", "rows")
DQ_RULE_VIEWS = (
    ("bad_geo", "dq_bad_geo"), ("duplicate_fir", "dq_duplicate_firs"), ("orphan_evidence", "dq_orphan_evidence"),
    ("stale_camera", "dq_stale_cameras"), ("time_inconsistent", "dq_time_inconsistent"),
    ("tip_without_incident", "dq_tip_without_incident"), ("unmapped_section", "dq_unmapped_sections"),
)


def _q_dq_summary(sample: bool) -> str:
    if not sample:
        parts = " UNION ALL ".join(f"SELECT '{rule}' AS rule, count(*) AS rows FROM nexus.{view}"
                                   for rule, view in DQ_RULE_VIEWS)
        return f"SELECT rule, rows FROM ({parts}) s ORDER BY rule"  # ORDER BY: D-031
    # Twin over the sample bundle: the crime rules use nexus-2's rule text (dq_rules.py), the evidence and tip
    # rules mirror 20_dq.sql over the bundle's tables. The bundle has no camera registry, so stale_camera is
    # NULL (not measured), never a 0 nobody counted.
    from . import dq_rules

    flags = dq_rules.flags_sql(dq_rules.DUCK, dq_rules.city_bounds(load_city(get_settings().city)))
    crime_rules = ", ".join(f"('{r}')" for r in dq_rules.RULES)
    return (
        "SELECT rule, rows FROM ("
        f"SELECT r.rule, count(f.rule) AS rows FROM (VALUES {crime_rules}) r(rule) "
        f"LEFT JOIN ({flags}) f ON f.rule = r.rule GROUP BY r.rule "
        "UNION ALL SELECT 'orphan_evidence', count(*) FROM 'sb/evidence_media.parquet' e "
        "WHERE e.crime_id NOT IN (SELECT crime_id FROM v_crime_unified) "
        "UNION ALL SELECT 'tip_without_incident', count(*) FROM 'sb/tips.parquet' t "
        "WHERE t.public_incident_id IS NULL AND t.status NOT IN ('quarantined', 'closed') "
        "UNION ALL SELECT 'stale_camera', CAST(NULL AS BIGINT)"
        ") s ORDER BY rule"
    )


def specs() -> dict[str, dict[str, Any]]:
    tz, off = _city_time()
    return {
        "q_case": {"name": "q_case", "lightning": _q_case_bundle(), "sample": _twin("q_case", CASE_COLUMNS),
                   "description": "One crime with vehicles, statements, evidence, forensics and features (D3.1)",
                   "columns": CASE_COLUMNS, "boolean": ("synthetic",)},
        "q_candidates": {"name": "q_candidates", "lightning": _q_candidates(tz, off),
                         "sample": _twin("q_candidates", CANDIDATE_COLUMNS),
                         "description": "Blocking: same-category crimes within :days and :ring km (F1 step 3)",
                         "columns": CANDIDATE_COLUMNS},
        "q_features": {"name": "q_features", "lightning": Q_FEATURES,
                       "sample": _twin("q_features", FEATURES_COLUMNS),
                       "description": "Extracted MO features for a comma-joined list of crime ids (D3.2)",
                       "columns": FEATURES_COLUMNS},
        "q_tip_corroboration": {"name": "q_tip_corroboration", "lightning": _q_tip_corroboration(tz),
                                "sample": _q_tip_corroboration_sample(tz), "defaults": {"days": 30},
                                "description": "Screened public tips in a crime's H3 r8 cell within :days (default 30)",
                                "columns": TIP_COLUMNS},
        "q_vehicle_trail": {"name": "q_vehicle_trail", "lightning": _q_vehicle_trail(tz, off, sample=False),
                            "sample": _q_vehicle_trail(tz, off, sample=True), "defaults": {"pad_days": 7},
                            "description": "ANPR reads of a plate pattern around :t0..:t1, each tied to the nearest "
                                           "crime scene within 1.5 km / 2 h",
                            "columns": TRAIL_COLUMNS},
        "q_offender_return": {"name": "q_offender_return", "lightning": _q_offender_return(tz, sample=False),
                              "sample": _q_offender_return(tz, sample=True),
                              "description": "Offenders released within 60 days of :since whose prior MO shares "
                                             ":mo_tags; home ward (:ward) first",
                              "columns": RETURN_COLUMNS,
                              # REST returns text; factors.offender_return compares mo_overlap with floats.
                              "numeric": ("mo_overlap", "days_since_release"),
                              "boolean": ("near_home", "sheet_active")},
        "q_calls_near": {"name": "q_calls_near", "lightning": _q_calls_near(tz, off, sample=False),
                         "sample": _q_calls_near(tz, off, sample=True), "defaults": {"km": 1.0, "minutes": 120},
                         "description": "112 calls within :km of a crime and :minutes of its time window",
                         "columns": CALLS_COLUMNS,
                         # REST returns text; the DuckDB twin returns numbers, so match it live.
                         "numeric": ("lat", "lon", "km_from_scene", "minutes_from_start")},
        # The 7 views do a 19,540-row self-join among other things: about 80 s live (26 Oct). Fail fast at
        # 180 s, one attempt; app.dq_status keeps the last good counts.
        "q_dq_summary": {"name": "q_dq_summary", "lightning": _q_dq_summary(sample=False),
                         "sample": _q_dq_summary(sample=True), "timeout_s": 180.0,
                         "description": "Row count of each data-quality rule view (System page, via app.dq_status)",
                         "columns": DQ_SUMMARY_COLUMNS},
    }
