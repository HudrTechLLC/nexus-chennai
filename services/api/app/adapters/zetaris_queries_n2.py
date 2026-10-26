"""Named queries owned by the engines lane (nexus-2), merged into NAMED_QUERIES by adapters/zetaris.py.

Split agreed with nexus-1 (data lane), who owns adapters/zetaris.py and the core registry.
Each query has a Lightning SQL form (Zetaris, schema `nexus`) and a DuckDB twin over the sample
bundle (data/sample/views.sql defines the same view names), and declares its output columns.

Lists come back as comma-joined strings in both forms (Spark `concat_ws(collect_list)`, DuckDB
`string_agg`), so the two return identical shapes.
"""

from __future__ import annotations

from .zetaris import NamedQuery

# Hotspot detector input (WS2-18): crimes per (h3_r9 cell, category, day) from baseline_since to until.
_HEX_COLUMNS = ("cell", "category", "day", "n", "crime_ids", "station_ids")

Q_HEX_COUNTS = NamedQuery(
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
def _dq_query() -> NamedQuery:
    from ..config import get_settings, load_city
    from . import dq_rules

    bounds = dq_rules.city_bounds(load_city(get_settings().city))
    return NamedQuery(
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

N2_QUERIES: dict[str, NamedQuery] = {q.name: q for q in (Q_HEX_COUNTS, Q_DQ_FLAGS)}
