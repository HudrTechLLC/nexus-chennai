"""zetaris/30_case.sql: q_case in one Postgres round trip (case_bundle_v). Parity vs live q_case was checked
against Zetaris on 6 crimes (vehicles, statements, features, evidence, bare); see the PR."""

import importlib.util
from pathlib import Path

import yaml

from app.adapters import case_bundle
from app.adapters.zetaris_queries_n1 import CASE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]


def test_committed_file_is_generated():
    committed = (ROOT / "zetaris" / "30_case.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == case_bundle.case_file(), "regenerate: cd services/api && python -m app.adapters.case_bundle"


def test_view_returns_the_q_case_contract_from_one_native_query():
    sql = case_bundle.view_sql()
    for col in CASE_COLUMNS:
        assert f" AS {col}" in sql or f"c.{col}," in sql or f"c.{col} " in sql or f"c.{col}\n" in sql, col
    assert sql.count("FROM public.") == 6                      # crimes + 5 correlated sub-selects, one trip
    assert "st_" not in sql.lower() and "extensions." not in sql  # zetaris_reader has no extensions USAGE
    assert "Asia/Kolkata" not in sql and "{{city:timezone}}" in sql   # D-004


def test_register_py_renders_it_with_the_city_timezone():
    spec = importlib.util.spec_from_file_location("register", ROOT / "zetaris" / "register.py")
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    city = yaml.safe_load((ROOT / "cities" / "chennai" / "city.yaml").read_text(encoding="utf-8"))
    (stmt,) = reg.statements((ROOT / "zetaris" / "30_case.sql").read_text(encoding="utf-8"))
    shown = reg.fill(stmt, city, "2026-09-26", "2026-10-26")[1]
    assert shown.startswith("CREATE DATASOURCE VIEW case_bundle_v FROM sb AS SELECT")
    assert "{{" not in shown and "'Asia/Kolkata'" in shown


def test_switch_text_for_q_case_is_one_filtered_read():
    sql = case_bundle.q_case_lightning(CASE_COLUMNS)
    assert sql.endswith("FROM sb.case_bundle_v WHERE crime_id = :crime_id")
