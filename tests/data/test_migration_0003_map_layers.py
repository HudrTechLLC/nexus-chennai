"""0003_map_layers: display-only projection tables (D-019) - RLS on, no anon, not for Zetaris."""

import re
from pathlib import Path

SQL = (Path(__file__).resolve().parents[2] / "supabase/migrations/0003_map_layers.sql").read_text(encoding="utf-8")
LOW = SQL.lower()
CODE = re.sub(r"--[^\n]*", "", LOW)
TABLES = {"map_cctv_cameras", "map_anpr_cameras", "map_anpr_reads", "map_call_cells", "map_release_density"}


def test_tables_have_rls_and_synthetic():
    assert set(re.findall(r"create table if not exists public\.(\w+)", LOW)) == TABLES
    for t in TABLES:
        assert f"alter table public.{t}" in LOW and "enable row level security" in LOW
    assert len(re.findall(r"^\s+synthetic\s+boolean not null default true", LOW, flags=re.M)) == len(TABLES)


def test_no_anon_and_not_federated():
    assert not re.search(r"grant [^;]* to [^;]*\banon\b", CODE)
    assert "zetaris_reader" not in CODE
    assert "never an agent source" in LOW


def test_calls_and_releases_are_aggregates():
    calls = LOW[LOW.index("public.map_call_cells ("):]
    calls = calls[: calls.index(");")]
    rel = LOW[LOW.index("public.map_release_density ("):]
    rel = rel[: rel.index(");")]
    for banned in ("caller", "lat ", "person"):
        assert banned not in calls and banned not in rel
