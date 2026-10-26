"""Data-lane named queries: registered, columns declared, SQL renders, city time from the pack."""

import re

from app.adapters.zetaris import NAMED_QUERIES, render
from app.adapters.zetaris_queries_n1 import CASE_COLUMNS, FEATURES_COLUMNS, specs


def test_registered_with_contract_columns():
    assert NAMED_QUERIES["q_case"].columns == CASE_COLUMNS
    assert NAMED_QUERIES["q_features"].columns == FEATURES_COLUMNS


def test_lightning_renders_with_only_declared_params():
    sql = render(NAMED_QUERIES["q_case"].lightning, {"crime_id": "CHN-AD-2026-001182"})
    assert "'CHN-AD-2026-001182'" in sql and ":crime_id" not in sql
    sql = render(NAMED_QUERIES["q_features"].lightning, {"ids": "A,B"})
    assert "split('A,B', ',')" in sql


def test_reads_only_registered_sources_and_safe_views():
    for name in ("q_case", "q_features"):
        sql = NAMED_QUERIES[name].lightning
        tables = set(re.findall(r"\bFROM\s+([a-z_]+\.[a-z_]+)", sql, flags=re.I))
        assert tables <= {"sb.crimes", "sb.crime_vehicles", "sb.statements", "sb.evidence_media", "sb.forensics",
                          "sb.crime_features_v"}, tables
        assert "sb.tips" not in sql


def test_city_time_comes_from_the_pack():
    sql = specs()["q_case"]["lightning"]
    assert "from_utc_timestamp(c.occurred_from, 'Asia/Kolkata')" in sql and "'+05:30'" in sql


def test_no_param_lookalikes_in_sql():
    # ':' followed by letters is parsed as a parameter by render(); time formats must not contain it
    for name in ("q_case", "q_features"):
        params = set(re.findall(r":([a-z_][a-z0-9_]*)", NAMED_QUERIES[name].lightning))
        assert params <= {"crime_id", "ids"}, params
