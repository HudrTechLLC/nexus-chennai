"""Live RLS checks for 0005 (engine tables) against Supabase, inside a transaction that is rolled back.

Skipped unless NEXUS_DB_PASSWORD is set for the command, read from the password file:

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/engines/test_engines_rls_live.py

Seeds two stations, an officer at station A, one crime at each, and a World Model graph
where one vehicle links both crimes. Checks what the officer, an analyst and anon can see,
and that the append-only tables refuse UPDATE/DELETE even for the owner. Nothing is committed.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

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
        if os.environ.get("NEXUS_TRY_0005_IN_TXN") == "1":
            # Pre-merge check: run the migration inside this transaction; the rollback below undoes it.
            sql = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0005_01_engines.sql")
            c.execute(sql.read_text(encoding="utf-8"))
        c.execute("select to_regclass('public.wm_entities')")
        if c.fetchone()[0] is None:
            pytest.skip("0005 not applied yet")
        yield c
        conn.rollback()


def _seed(cur):
    sfx = uuid.uuid4().hex[:6].upper()
    a, b = f"PS-WM-A{sfx}", f"PS-WM-B{sfx}"
    officer, analyst = str(uuid.uuid4()), str(uuid.uuid4())
    cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,'A','law_and_order',true),"
                "(%s,'B','law_and_order',true)", (a, b))
    for uid, role, st in ((officer, "station_officer", a), (analyst, "analyst", None)):
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid[:8]}@example.invalid"))
        cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,'T',%s,%s)", (uid, role, st))
    own, other = f"CHN-WA-{sfx}", f"CHN-WB-{sfx}"
    for cid, st in ((own, a), (other, b)):
        cur.execute(
            "insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
            " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','robbery',now(),now(),"
            "13.0,80.25,3,'n','a','88abc','2026-W43',true)", (cid, st))
    bike, phone = f"vehicle:plate:TN09T{sfx}", f"phone:msisdn:98{sfx}"
    ents = [(f"crime:fir:{own}", "crime", own), (f"crime:fir:{other}", "crime", other),
            (bike, "vehicle", f"TN09T{sfx}"), (phone, "phone", f"98{sfx}")]
    for eid, t, k in ents:
        cur.execute("insert into public.wm_entities (id, type, key, synthetic) values (%s,%s,%s,true)", (eid, t, k))
    edges = [(f"rel_a{sfx}", f"crime:fir:{own}", bike, own), (f"rel_b{sfx}", f"crime:fir:{other}", bike, other),
             (f"rel_c{sfx}", f"crime:fir:{other}", phone, other)]
    for rid, f, t, c in edges:
        cur.execute("insert into public.wm_edges (id, from_id, type, to_id, crime_id, synthetic) "
                    "values (%s,%s,'used_vehicle',%s,%s,true)", (rid, f, t, c))
    cur.execute("insert into public.wm_observations (id, subject_id, source, synthetic) values (%s,%s,'test',true)",
                (f"obs_{sfx}", phone))
    cur.execute("insert into public.hmem_memories (id, store, memory_id, content, confidence, layer, alert_id, "
                "synthetic) values (%s,'t',%s,'x',0.8,'working','LA-NOT-AN-FK',true)", (f"t:mem-{sfx}", f"mem-{sfx}"))
    cur.execute("insert into public.hmem_ledger (store, memory_id, action, actor, at, entry_hash, synthetic) "
                "values ('t',%s,'create','analyst',now(),%s,true)", (f"mem-{sfx}", f"h{sfx}"))
    return officer, analyst, own, other, bike, phone, sfx


def _as_user(cur, user_id):
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user_id, "role": "authenticated"}),))


def test_officer_sees_own_crime_graph_but_not_other_stations(cur):
    officer, _, own, other, bike, phone, sfx = _seed(cur)
    _as_user(cur, officer)
    cur.execute("select id from public.wm_entities where id like %s or id = %s or id = %s",
                (f"crime:fir:CHN-W_-{sfx}", bike, phone))
    seen = {r[0] for r in cur.fetchall()}
    assert seen == {f"crime:fir:{own}", bike}       # the shared bike yes; other crime and its phone no
    cur.execute("select crime_id from public.wm_edges where id like %s", (f"rel_%{sfx}",))
    assert {r[0] for r in cur.fetchall()} == {own}
    cur.execute("select count(*) from public.wm_observations where id = %s", (f"obs_{sfx}",))
    assert cur.fetchone()[0] == 0                   # the phone's provenance is hidden too


def test_analyst_sees_the_whole_graph(cur):
    _, analyst, own, other, bike, phone, sfx = _seed(cur)
    _as_user(cur, analyst)
    cur.execute("select count(*) from public.wm_entities where id in (%s,%s,%s,%s)",
                (f"crime:fir:{own}", f"crime:fir:{other}", bike, phone))
    assert cur.fetchone()[0] == 4
    cur.execute("select count(*) from public.hmem_memories where id = %s", (f"t:mem-{sfx}",))
    assert cur.fetchone()[0] == 1


def test_authenticated_cannot_write(cur):
    officer, *_ = _seed(cur)
    _as_user(cur, officer)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("insert into public.wm_entities (id, type, key) values ('x','vehicle','x')")


def test_append_only_tables_refuse_update_and_delete_even_for_owner(cur):
    *_, sfx = _seed(cur)
    cur.execute("savepoint s")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("update public.hmem_ledger set actor = 'x' where entry_hash = %s", (f"h{sfx}",))
    cur.execute("rollback to savepoint s")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute("delete from public.wm_observations where id = %s", (f"obs_{sfx}",))


def test_anon_reads_nothing(cur):
    cur.execute("set local role anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("select 1 from public.wm_entities limit 1")
