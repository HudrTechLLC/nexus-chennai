"""Live checks for tips at H3 r8-r10 (0007_12, WS4-15 part C), inside a transaction that is rolled back.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/console/test_tip_fine_cell_live.py

Loads the migration in-transaction when it is not applied. Seeds a station, an analyst and a crime inside the
transaction. Nothing is committed.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
h3 = pytest.importorskip("h3")
pytestmark = pytest.mark.skipif(not os.environ.get("NEXUS_DB_PASSWORD"), reason="live DB check (needs NEXUS_DB_PASSWORD)")

REF = os.environ.get("NEXUS_SUPABASE_REF", "ukrujnsjucwvytnokbtw")
HOSTS = [os.environ.get("NEXUS_DB_HOST", ""), "aws-0-ap-southeast-1.pooler.supabase.com",
         "aws-1-ap-southeast-1.pooler.supabase.com"]
MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0007_12_tip_fine_cell.sql"
ADYAR = (13.0067, 80.2575)


@pytest.fixture()
def cur():
    conn = None
    for host in [h for h in HOSTS if h]:
        try:
            conn = psycopg.connect(host=host, port=5432, dbname="postgres", user=f"postgres.{REF}",
                                   password=os.environ["NEXUS_DB_PASSWORD"], sslmode="require", connect_timeout=15)
            break
        except psycopg.OperationalError:
            continue
    assert conn is not None, "could not connect"
    with conn:
        c = conn.cursor()
        c.execute("set local search_path = public, extensions")
        c.execute(MIGRATION.read_text(encoding="utf-8"))  # create-or-replace / idempotent: safe in a rolled-back txn
        c.execute("reset search_path")
        yield c
        conn.rollback()


def _as(cur, uid: str | None):
    cur.execute("reset role")
    if uid is None:
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
        cur.execute("set local role anon")
        return
    cur.execute("select set_config('request.jwt.claims', %s, true), set_config('request.jwt.claim.sub', %s, true)",
                (json.dumps({"sub": uid, "role": "authenticated"}), uid))
    cur.execute("set local role authenticated")


def _submit(cur, cell: str) -> dict:
    cur.execute("select public.submit_tip(null, 'vehicle_seen', 'A red bike near the bus stop', %s, false,"
                " null, null, '[]'::jsonb, 'Asia/Kolkata', null)", (cell,))
    return cur.fetchone()[0]


def test_parent_matches_the_h3_library(cur):
    rng = random.Random(7)
    cells = []
    for _ in range(120):
        lat, lon = 12.9 + rng.random() * 0.3, 80.1 + rng.random() * 0.2
        cells += [h3.latlng_to_cell(lat, lon, r) for r in (8, 9, 10)]
    cur.execute("select c, public.h3_parent_r8(c) from unnest(%s::text[]) c", (cells,))
    got = dict(cur.fetchall())
    assert all(got[c] == h3.cell_to_parent(c, 8) for c in cells)
    r8 = h3.latlng_to_cell(*ADYAR, 8)
    cur.execute("select public.h3_parent_r8(%s)", (r8,))
    assert cur.fetchone()[0] == r8  # an r8 cell is its own parent


@pytest.mark.parametrize("bad", ["87618c2b7ffffff", "8b618c2b0100fff", "88618C2B7FFFFFF", "nonsense"])
def test_submit_tip_refuses_other_resolutions(cur, bad):
    _as(cur, None)
    cur.execute("savepoint s")
    with pytest.raises(psycopg.Error):
        _submit(cur, bad)
    cur.execute("rollback to savepoint s")


def test_r10_tip_stores_its_r8_parent_and_appears_in_triage_nearby(cur):
    sfx = uuid.uuid4().hex[:6].upper()
    r10 = h3.latlng_to_cell(*ADYAR, 10)
    r8 = h3.cell_to_parent(r10, 8)
    st = f"PS-CELL-{sfx}"
    cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,%s,'law_and_order',true)", (st, st))
    analyst = str(uuid.uuid4())
    cur.execute("insert into auth.users (id, email) values (%s, %s)", (analyst, f"cell-{sfx}@example.invalid"))
    cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,'A','analyst',%s)", (analyst, st))
    crime = f"CHN-CL-{sfx}"
    cur.execute("insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
                " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','chain_snatching',now(),"
                "now(),%s,%s,3,'n','a',%s,'2026-W44',true)", (crime, st, ADYAR[0], ADYAR[1], r8))

    _as(cur, None)  # the public submits, anonymously
    tip_id = _submit(cur, r10)["tip_id"]
    cur.execute("reset role")
    cur.execute("select approx_cell, approx_cell_fine from public.tips where tip_id = %s", (tip_id,))
    assert cur.fetchone() == (r8, r10)

    _as(cur, analyst)  # triage, under RLS
    cur.execute("select public.tip_nearby_crimes(%s)", (tip_id,))
    assert crime in [c["crime_id"] for c in cur.fetchone()[0]]


def test_weekly_cap_counts_on_the_r8_parent(cur):
    r8 = h3.latlng_to_cell(*ADYAR, 8)
    kids = list(h3.cell_to_children(r8, 10))
    cur.execute("select public.iso_week(now(), 'Asia/Kolkata')")
    wk = cur.fetchone()[0]
    cur.execute("insert into public.tips (tip_id, channel, category, text, approx_cell, received_week, status, synthetic)"
                " select 'TIP-CAP' || g, 'web', 'something_else', 'x', %s, %s, 'new', true from generate_series(1, 200) g",
                (r8, wk))
    _as(cur, None)
    cur.execute("savepoint s")
    with pytest.raises(psycopg.Error, match="too many tips"):
        _submit(cur, kids[0])  # a finer cell does not dodge the cap of its r8 area
    cur.execute("rollback to savepoint s")
