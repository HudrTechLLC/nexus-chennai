"""Static checks on supabase/migrations/0002_core.sql (CI has no database).

The live RLS behaviour is checked by tests/data/test_rls_live.py against Supabase.
"""

from __future__ import annotations

import re
from pathlib import Path

SQL = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0002_core.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()

# Part I tables (0001 holds stations, wards, profiles, runs).
PART_I = {
    "section_map", "crimes", "crime_features", "persons", "person_links", "crime_vehicles", "evidence_media",
    "statements", "case_diary", "forensics", "missing_persons", "public_incidents", "tips", "tip_media",
    "tip_messages", "link_alerts", "link_factors", "alert_decisions", "series", "series_members", "taskforces",
    "taskforce_members", "notifications", "outbox", "audit_log",
}


def created_tables() -> set[str]:
    return set(re.findall(r"create table if not exists public\.(\w+)", LOWER))


def test_every_part_i_table_is_created():
    assert created_tables() == PART_I


def test_every_table_has_rls():
    rls = set(re.findall(r"alter table public\.(\w+)\s+enable row level security", LOWER))
    assert created_tables() <= rls


def test_anon_gets_nothing():
    for stmt in (
        "revoke all on all tables in schema public from anon",
        "revoke all on all sequences in schema public from anon",
        "revoke all on all functions in schema public from anon",
        "alter default privileges in schema public revoke all on tables from anon",
    ):
        assert stmt in LOWER
    code = re.sub(r"--[^\n]*", "", LOWER)  # the rollback note is a comment, not a grant
    assert not re.search(r"grant [^;]* to [^;]*\banon\b", code), "0002 must never grant anything to anon"


def test_citywide_view_is_invoker_and_summary_only():
    assert "create or replace view public.crimes_citywide with (security_invoker = true)" in LOWER
    fn = LOWER[LOWER.index("create or replace function public.crimes_citywide_rows()"):]
    fn = fn[: fn.index("$$;")]
    returns = fn[fn.index("returns table"): fn.index("language")]
    for secret in ("narrative", "address", "lat", "lon", "geom", "victims", "property", "fir_no"):
        assert not re.search(rf"\b{secret}\b", returns), secret


def test_tips_store_no_exact_time_or_identity():
    tips = LOWER[LOWER.index("create table if not exists public.tips ("):]
    tips = tips[: tips.index(");")]
    for banned in ("created_at", "ip", "user_agent", "email", "phone", "device"):
        assert not re.search(rf"^\s+{banned}\b", tips, flags=re.M), banned
    assert "received_week" in tips


def test_decisions_insert_is_analyst_and_up_and_self():
    pol = LOWER[LOWER.index('create policy "analysts decide alerts"'):]
    pol = pol[: pol.index(";")]
    assert "'analyst', 'supervisor', 'admin'" in pol and "by = auth.uid()" in pol


def test_zetaris_reader_is_read_only():
    grants = re.findall(r"grant ([a-z, ]+) on [^;]* to zetaris_reader", LOWER)
    assert grants and all(g.strip() == "select" for g in grants)


def test_has_rollback_note():
    assert "-- rollback:" in LOWER
