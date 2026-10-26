"""Static checks on supabase/migrations/0005_01_engines.sql (CI has no database).
Live RLS behaviour: tests/engines/test_engines_rls_live.py."""

import re
from pathlib import Path

SQL = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0005_01_engines.sql").read_text(
    encoding="utf-8")
LOWER = SQL.lower()
CODE = re.sub(r"--[^\n]*", "", LOWER)
TABLES = {"wm_entities", "wm_edges", "wm_observations", "hmem_memories", "hmem_ledger"}


def test_creates_exactly_the_contract_tables():
    assert set(re.findall(r"create table if not exists public\.(\w+)", CODE)) == TABLES


def test_every_table_has_rls_and_a_select_policy():
    assert set(re.findall(r"alter table public\.(\w+)\s+enable row level security", CODE)) == TABLES
    assert {t for t in TABLES if re.search(rf"create policy \"[^\"]+\" on public\.{t} for select to authenticated", CODE)} \
        == TABLES


def test_anon_gets_nothing_and_authenticated_only_reads():
    assert not re.search(r"grant [^;]*\banon\b", CODE)
    grants = re.findall(r"grant ([^;]*?) on (?:table )?public\.(\w+)", CODE)
    assert all(g.strip() == "select" for g, _ in grants)
    assert not re.search(r"create policy [^;]* for (insert|update|delete|all)", CODE)


def test_ledger_and_observations_are_append_only():
    for t in ("wm_observations", "hmem_ledger"):
        assert re.search(rf"before update or delete on public\.{t}\s+for each row execute function "
                         r"public\.engines_append_only\(\)", CODE), t


def test_alert_id_is_plain_text_without_fk():
    block = CODE[CODE.index("create table if not exists public.hmem_memories"):]
    block = block[: block.index(");")]
    assert re.search(r"\balert_id\s+text,", block) and "references" not in block


def test_station_officer_scope_uses_can_read_crime():
    fn = CODE[CODE.index("create or replace function public.wm_can_read_entity"):]
    fn = fn[: fn.index("$$;")]
    assert "can_read_crime(p_key)" in fn and "can_read_crime(e.crime_id)" in fn
    assert "security definer" in fn and "set search_path = public" in fn


def test_rollback_block_present():
    assert "-- rollback:" in LOWER and "drop table if exists public.hmem_ledger" in LOWER
