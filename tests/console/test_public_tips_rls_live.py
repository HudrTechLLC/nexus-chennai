"""WS3-28 "From the public": the loader's queries under RLS, inside a transaction that is rolled back.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/console/test_public_tips_rls_live.py

Mirrors apps/web/lib/publicTipsData.ts step by step as a station officer and as an analyst. Police may read
every tip (0002), so the can_read_crime gate is the first step: tips are only looked up for crimes the viewer
can read, which `crimes` returns under its RLS. Seeds two stations, a crime at each, an appeal, and tips tied
by appeal, by crime card, by review, plus a quarantined one. Nothing is committed.
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
TIP_COLUMNS = "tip_id, received_week, category, status, approx_cell, approx_cell_fine, public_incident_id, about_crime_id"


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
        yield conn.cursor()
        conn.rollback()


def _as(cur, uid: str):
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true), set_config('request.jwt.claim.sub', %s, true)",
                (json.dumps({"sub": uid, "role": "authenticated"}), uid))
    cur.execute("set local role authenticated")


def _seed(cur) -> dict[str, str]:
    sfx = uuid.uuid4().hex[:6].upper()
    out: dict[str, str] = {}
    for tag in ("A", "B"):
        st = f"PS-PT{tag}-{sfx}"
        cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,%s,'law_and_order',true)", (st, st))
        crime = f"CHN-P{tag}-{sfx}"
        cur.execute("insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
                    " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','robbery',now(),now(),"
                    "13.0,80.25,3,'n','a','88618c4f41fffff','2026-W44',true)", (crime, st))
        out[f"st{tag}"], out[f"crime{tag}"] = st, crime
    for role, key, st in (("station_officer", "officerA", out["stA"]), ("analyst", "analyst", out["stA"])):
        uid = str(uuid.uuid4())
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"pt-{key}-{sfx}@example.invalid"))
        cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,%s,%s,%s)", (uid, key, role, st))
        out[key] = uid
    pid = f"PI-PT-{sfx}"
    cur.execute("insert into public.public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week,"
                " time_window, summary) values (%s,%s,'t','robbery','Area','88618c4f41fffff','2026-W43','Evening','s')",
                (pid, out["crimeA"]))
    out["appeal"] = pid

    def tip(name: str, **kw):
        tid = f"TIP-{name}-{sfx}"
        cols = {"tip_id": tid, "channel": "web", "category": "vehicle_seen", "text": "x", "received_week": "2026-W43",
                "status": "screened", "synthetic": True, "approx_cell": "88618c4f41fffff", **kw}
        cur.execute(f"insert into public.tips ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})", list(cols.values()))
        out[name] = tid

    tip("APPEAL", public_incident_id=pid, approx_cell_fine="8a618c4f4107fff")
    tip("ABOUTA", about_crime_id=out["crimeA"])
    tip("ABOUTB", about_crime_id=out["crimeB"])  # another station's case
    tip("REVIEWED")
    tip("QUAR", about_crime_id=out["crimeA"], status="quarantined")
    cur.execute("insert into public.tip_reviews (tip_id, useful, crime_id, by) values (%s, true, %s, %s)",
                (out["REVIEWED"], out["crimeA"], out["analyst"]))
    return out


def _load(cur, crime_ids: list[str]) -> tuple[set[str], set[str]]:
    """publicTipsData.fetchPublicTips, step for step. Returns (readable crimes, tied tip ids incl. quarantined)."""
    cur.execute("select crime_id from public.crimes where crime_id = any(%s)", (crime_ids,))
    ok = [r[0] for r in cur.fetchall()]
    if not ok:
        return set(), set()
    cur.execute("select public_incident_id from public.public_incidents where crime_id = any(%s)", (ok,))
    appeals = [r[0] for r in cur.fetchall()]
    cur.execute(f"select {TIP_COLUMNS} from public.tips where about_crime_id = any(%s)", (ok,))
    tips = {r[0] for r in cur.fetchall()}
    cur.execute("select tip_id from public.tip_reviews where crime_id = any(%s)", (ok,))
    reviewed = [r[0] for r in cur.fetchall()]
    cur.execute(f"select {TIP_COLUMNS} from public.tips where public_incident_id = any(%s) or tip_id = any(%s)",
                (appeals, reviewed))
    tips |= {r[0] for r in cur.fetchall()}
    return set(ok), tips


def test_station_officer_sees_only_tips_on_own_station_cases(cur):
    u = _seed(cur)
    _as(cur, u["officerA"])
    readable, tips = _load(cur, [u["crimeA"], u["crimeB"]])
    assert readable == {u["crimeA"]}  # can_read_crime: the other station's case is not read in full
    assert tips == {u["APPEAL"], u["ABOUTA"], u["REVIEWED"], u["QUAR"]}  # QUAR is fetched, then dropped by linkPublicTips
    assert u["ABOUTB"] not in tips


def test_analyst_sees_tips_on_every_case(cur):
    u = _seed(cur)
    _as(cur, u["analyst"])
    readable, tips = _load(cur, [u["crimeA"], u["crimeB"]])
    assert readable == {u["crimeA"], u["crimeB"]}
    assert {u["APPEAL"], u["ABOUTA"], u["ABOUTB"], u["REVIEWED"]} <= tips


def test_fine_cell_column_is_readable_by_police(cur):
    u = _seed(cur)
    _as(cur, u["officerA"])
    cur.execute("select approx_cell, approx_cell_fine from public.tips where tip_id = %s", (u["APPEAL"],))
    assert cur.fetchone() == ("88618c4f41fffff", "8a618c4f4107fff")
