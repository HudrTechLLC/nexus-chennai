"""Live RLS checks against the Supabase database, inside a transaction that is rolled back.

Skipped unless NEXUS_DB_PASSWORD is set for the command, read from the password file:

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/data/test_rls_live.py

It creates two stations, a station officer at station A, and one crime at each station,
then checks what the officer and anon can see. Nothing is committed.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(not os.environ.get("NEXUS_DB_PASSWORD"), reason="live DB check (needs NEXUS_DB_PASSWORD)")

REF = os.environ.get("NEXUS_SUPABASE_REF", "ukrujnsjucwvytnokbtw")
HOSTS = [os.environ.get("NEXUS_DB_HOST", ""), "aws-0-ap-southeast-1.pooler.supabase.com",
         "aws-1-ap-southeast-1.pooler.supabase.com"]


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
        yield c
        conn.rollback()


def _seed(cur):
    sfx = uuid.uuid4().hex[:6].upper()
    a, b = f"PS-TEST-A{sfx}", f"PS-TEST-B{sfx}"
    officer = str(uuid.uuid4())
    cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,'A','law_and_order',true),"
                "(%s,'B','law_and_order',true)", (a, b))
    cur.execute("insert into auth.users (id, email) values (%s, %s)", (officer, f"t{sfx}@example.invalid"))
    cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,'T','station_officer',%s)",
                (officer, a))
    for cid, st in ((f"CHN-TA-{sfx}", a), (f"CHN-TB-{sfx}", b)):
        cur.execute(
            "insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
            " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','robbery',now(),now(),"
            "13.0,80.25,3,'SECRET NARRATIVE','SECRET ADDRESS','88abc','2026-W43',true)", (cid, st))
    return officer, f"CHN-TA-{sfx}", f"CHN-TB-{sfx}"


def _as_user(cur, user_id):
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user_id, "role": "authenticated"}),))


def test_officer_sees_only_own_station_full_rows(cur):
    officer, own, other = _seed(cur)
    _as_user(cur, officer)
    cur.execute("select crime_id from public.crimes where crime_id in (%s, %s)", (own, other))
    assert [r[0] for r in cur.fetchall()] == [own]


def test_citywide_has_other_station_but_no_narrative_or_address(cur):
    officer, own, other = _seed(cur)
    _as_user(cur, officer)
    cur.execute("select * from public.crimes_citywide where crime_id = %s", (other,))
    row = cur.fetchone()
    cols = [d.name for d in cur.description]
    assert row is not None and row[cols.index("cell")] == "88abc"
    assert not {"narrative", "address", "lat", "lon", "geom"} & set(cols)
    assert "SECRET" not in json.dumps([str(v) for v in row])


def test_anon_cannot_read_any_relation(cur):
    cur.execute(
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind in ('r','v','m','p') "
        "and has_table_privilege('anon', c.oid, 'select')")
    assert cur.fetchall() == []


def test_anon_select_is_denied(cur):
    cur.execute("set local role anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("select 1 from public.crimes_citywide limit 1")
