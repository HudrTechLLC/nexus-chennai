"""Data-quality rules over v_crime_unified (WS1-14, spec E5 "DQ views"). Owner: nexus-2.

One rule text, rendered for two dialects, so the Zetaris views (zetaris/20_dq.sql) and the DuckDB
twin of q_dq_flags apply exactly the same checks:

- duplicate_fir:      the same incident filed twice: same category, start times within DUP_WINDOW_MIN
                      minutes, coordinates within DUP_MAX_DEG degrees (~275 m; two stations often geocode
                      one incident into neighbouring H3 cells), and a different station or source system;
- bad_geo:            no coordinates, or outside the city's bounding box;
- time_inconsistent:  occurred after it was reported, or the occurrence ends before it starts;
- unmapped_section:   a legacy row whose IPC sections could not be mapped (sections_raw kept).

Not crime-level (Zetaris views only): dq_orphan_evidence, dq_tip_without_incident, dq_stale_cameras
(camera registry not updated in STALE_CAMERA_DAYS days).

City bounds come from cities/<city>/city.yaml `map.bounds` (D-004): nothing city-specific in code.
Every rule returns (crime_id, rule, other_id, detail).

Threshold note: DUP_WINDOW_MIN and DUP_MAX_DEG were chosen against the generator's planted duplicates
(_truth/duplicates.json, seed 42): recall 15/15, precision 15/15. Exact-cell matching scored 11/15.
"""

from __future__ import annotations

from typing import Any

DUP_WINDOW_MIN = 30
DUP_MAX_DEG = 0.0025
STALE_CAMERA_DAYS = 180
RULES = ("duplicate_fir", "bad_geo", "time_inconsistent", "unmapped_section")
COLUMNS = ("crime_id", "rule", "other_id", "detail")

# Live source for the crime-level rules: the unified crime view (nexus-1's 10_views.sql, live), so legacy rows
# take part in cross-source duplicates and unmapped_section.
# Source prefixes are placeholders (WS1-19): register.py fills {{src:sb}} / {{src:nexus}} from
# adapters/zetaris_sources.SOURCES, for --data supabase (sb, nexus) or files (nexus_fs, nexusfs).
SB = "{{src:sb}}"
NX = "{{src:nexus}}"
SPARK_VIEW = f"{NX}.v_crime_unified"
# Second side of the duplicate self-join. Zetaris cannot reference one schema-store view twice in a query
# (MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION, whatever the shape), so live the other record
# comes from sb.crimes, the system of record: a duplicate is any unified record that matches a record there.
# Two legacy-only records duplicating each other are not caught live (none are planted; _truth's 15 are all
# sb.crimes pairs). The DuckDB twin has no such limit and joins the view to itself.
SPARK = {"epoch": "unix_timestamp({x})", "str": "STRING", "view": SPARK_VIEW, "dup_side": f"{SB}.crimes"}
DUCK = {"epoch": "epoch({x})", "str": "VARCHAR", "view": "v_crime_unified", "dup_side": "v_crime_unified"}


def city_bounds(city: dict[str, Any]) -> dict[str, float]:
    west, south, east, north = (float(x) for x in city["map"]["bounds"])
    return {"west": west, "south": south, "east": east, "north": north}


def rule_sql(rule: str, d: dict[str, str], bounds: dict[str, float]) -> str:
    v, s = d["view"], d["str"]

    def ep(x: str) -> str:
        return d["epoch"].format(x=x)

    if rule == "duplicate_fir":
        # The other record, as a renamed projection of d["dup_side"] (see SPARK above).
        b_side = (f"(SELECT crime_id AS b_id, source AS b_source, station_id AS b_station, category AS b_category, "
                  f"occurred_from AS b_from, lat AS b_lat, lon AS b_lon FROM {d['dup_side']})")
        gap = f"abs({ep('a.occurred_from')} - {ep('b.b_from')})"
        return (
            f"SELECT a.crime_id AS crime_id, 'duplicate_fir' AS rule, b.b_id AS other_id, "
            f"concat('same ', a.category, ' within ', CAST(CAST({gap} / 60 AS INT) AS {s}), ' min and ', "
            f"CAST(CAST(greatest(abs(a.lat - b.b_lat), abs(a.lon - b.b_lon)) * 111000 AS INT) AS {s}), "
            f"' m, filed at ', coalesce(b.b_station, '?'), ' via ', b.b_source) AS detail "
            f"FROM {v} a JOIN {b_side} b ON a.category = b.b_category AND a.crime_id <> b.b_id "
            f"AND {gap} <= {DUP_WINDOW_MIN * 60} "
            f"AND abs(a.lat - b.b_lat) <= {DUP_MAX_DEG} AND abs(a.lon - b.b_lon) <= {DUP_MAX_DEG} "
            f"AND (coalesce(a.station_id, '') <> coalesce(b.b_station, '') OR a.source <> b.b_source)"
        )
    if rule == "bad_geo":
        return (
            f"SELECT crime_id, 'bad_geo' AS rule, CAST(NULL AS {s}) AS other_id, "
            f"CASE WHEN lat IS NULL OR lon IS NULL THEN 'no coordinates' "
            f"ELSE concat('outside city bounds: ', CAST(lat AS {s}), ', ', CAST(lon AS {s})) END AS detail "
            f"FROM {v} c WHERE lat IS NULL OR lon IS NULL OR lon < {bounds['west']} OR lon > {bounds['east']} "
            f"OR lat < {bounds['south']} OR lat > {bounds['north']}"
        )
    if rule == "time_inconsistent":
        return (
            f"SELECT crime_id, 'time_inconsistent' AS rule, CAST(NULL AS {s}) AS other_id, "
            f"CASE WHEN occurred_from > reported_at THEN 'occurred after it was reported' "
            f"ELSE 'occurrence ends before it starts' END AS detail "
            f"FROM {v} c WHERE occurred_from > reported_at OR occurred_to < occurred_from"
        )
    if rule == "unmapped_section":
        return (
            f"SELECT crime_id, 'unmapped_section' AS rule, CAST(NULL AS {s}) AS other_id, "
            f"concat('legacy sections not mapped: ', sections_raw) AS detail "
            f"FROM {v} c WHERE sections_raw IS NOT NULL"
        )
    raise KeyError(rule)


def flags_sql(d: dict[str, str], bounds: dict[str, float]) -> str:
    return " UNION ALL ".join(rule_sql(r, d, bounds) for r in RULES)


# ---------------------------------------------------------------------------- zetaris/20_dq.sql

# register.py fills these from the city pack (D-004), like {{since}} / {{until}}.
# register.py resolves {{city:...}} by dotted path with list indices; map.bounds is [west, south, east, north].
BOUND_PLACEHOLDERS = {k: "{{city:map.bounds.%d}}" % i for i, k in enumerate(("west", "south", "east", "north"))}

_HEADER = """-- zetaris/20_dq.sql · Data-quality views (spec E5, WS1-14). Owner: nexus-2 (engines lane).
-- GENERATED by `python -m app.adapters.dq_rules` from services/api/app/adapters/dq_rules.py, the same
-- rule text the q_dq_flags DuckDB twin runs. Do not edit by hand; tests/engines/test_dq.py checks it.
-- One statement per call; register.py strips the trailing semicolons and fills {{city:...}} from
-- cities/<city>/city.yaml. Views live in schema-store container `nexus` (queried as nexus.<view>), created
-- first here; there is no IF NOT EXISTS, and register.py skips "already exists", so other files may repeat it.
-- Crime-level rules read nexus.v_crime_unified (SPARK_VIEW in dq_rules.py).
"""
CONTAINER = f"CREATE SCHEMASTORE CONTAINER {NX};\n"


def dq_file() -> str:
    b = BOUND_PLACEHOLDERS
    views = [(f"dq_{name}", rule_sql(rule, SPARK, b)) for name, rule in (
        ("duplicate_firs", "duplicate_fir"), ("bad_geo", "bad_geo"), ("time_inconsistent", "time_inconsistent"),
        ("unmapped_sections", "unmapped_section"))]
    # Live, dq_flags unions the per-rule views: one query may not reference v_crime_unified more than once.
    views.append(("dq_flags", " UNION ALL ".join(f"SELECT {', '.join(COLUMNS)} FROM {NX}.{name}" for name, _ in views)))
    views.append(("dq_orphan_evidence",
                  "SELECT e.evidence_id, e.crime_id, 'evidence for a crime that does not exist' AS detail "
                  f"FROM {SB}.evidence_media e LEFT JOIN {NX}.v_crime_unified c ON c.crime_id = e.crime_id "
                  "WHERE c.crime_id IS NULL"))
    views.append(("dq_tip_without_incident",
                  "SELECT t.tip_id, t.category, t.received_week, 'tip not tied to a public incident' AS detail "
                  f"FROM {SB}.tips_v t WHERE t.public_incident_id IS NULL AND t.status NOT IN ('quarantined', 'closed')"))
    stale = f"datediff(current_date(), CAST(last_updated AS DATE)) > {STALE_CAMERA_DAYS}"
    views.append(("dq_stale_cameras",
                  "SELECT camera_id, owner_type, contact_station, last_updated, "
                  "concat('camera registry not updated for ', "
                  "CAST(datediff(current_date(), CAST(last_updated AS DATE)) AS STRING), ' days') AS detail "
                  f"FROM s3csv.cctv_cameras WHERE {stale}"))
    # ORDER BY on every view (D-031): Zetaris pushes the REST row limit, and count(*), into the JDBC scan ahead
    # of any filter it cannot push to Postgres, so an unsorted view returns the first N rows filtered, or the
    # unfiltered count. A sort above the filter blocks that pushdown.
    order = {"dq_flags": "crime_id, rule", "dq_orphan_evidence": "evidence_id", "dq_tip_without_incident": "tip_id",
             "dq_stale_cameras": "camera_id"}
    body = "\n".join(f"CREATE OR REPLACE SCHEMASTORE VIEW {name} WITH CONTAINER {NX} AS\n{sql}\n"
                     f"ORDER BY {order.get(name, 'crime_id')};\n" for name, sql in views)
    return _HEADER + "\n" + CONTAINER + "\n" + body


if __name__ == "__main__":
    from pathlib import Path

    out = Path(__file__).resolve().parents[4] / "zetaris" / "20_dq.sql"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dq_file(), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
