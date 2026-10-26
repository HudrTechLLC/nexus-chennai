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

# name -> (DuckDB sample SQL, output columns)
TWINS: dict[str, tuple[str, tuple[str, ...]]] = {
    "q_case": (_CASE_SAMPLE, CASE_COLUMNS),
    "q_features": (_FEATURES_SAMPLE, FEATURES_COLUMNS),
}
