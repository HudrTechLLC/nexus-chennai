"""0007_17 onboarding_decide on the live DB, in a rolled-back transaction: a combined Lat/Long column satisfies lat and
lon; a separate lon column as well is refused; a non-admin cannot decide.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/console/test_onboarding_decide_live.py
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
MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0007_17_onboarding_latlong.sql"


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
        c.execute(MIGRATION.read_text(encoding="utf-8"))  # create-or-replace: safe in a rolled-back transaction
        yield c
        conn.rollback()


def _user(cur, role: str) -> str:
    uid = str(uuid.uuid4())
    cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"onb-{role}-{uid[:6]}@example.invalid"))
    cur.execute("insert into public.profiles (user_id, name, role) values (%s, %s, %s)", (uid, role, role))
    return uid


def _as(cur, uid: str) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true), set_config('request.jwt.claim.sub', %s, true)",
                (json.dumps({"sub": uid, "role": "authenticated"}), uid))
    cur.execute("set local role authenticated")


def _run(cur, extra: list[tuple[str, str | None, str]] = ()) -> str:
    cur.execute("reset role")
    rid = str(uuid.uuid4())
    cur.execute("insert into public.onboarding_runs (run_id, source_key, label, use_sample, status) "
                "values (%s, %s, 'Live test', true, 'proposed')", (rid, f"t_{rid[:8]}"))
    rows = [("FIR No.", "fir_no", "none"), ("Date of Occurrence", "occurred_from", "date_dmy"),
            ("Lat/Long", "lat", "latlong_lat"), ("Crime Head", "category", "none"), *extra]
    for col, field, t in rows:
        cur.execute("insert into public.onboarding_mappings (run_id, source_col, unified_field, transform) "
                    "values (%s, %s, %s, %s)", (rid, col, field, t))
    return rid


def test_a_combined_lat_long_column_satisfies_lat_and_lon(cur):
    admin = _user(cur, "admin")
    rid = _run(cur)
    _as(cur, admin)
    cur.execute("select public.onboarding_decide(%s, 'approve')", (rid,))
    assert cur.fetchone()[0] == "approved"


def test_a_separate_lon_column_as_well_is_refused(cur):
    admin = _user(cur, "admin")
    rid = _run(cur, [("Longitude", "lon", "none")])
    _as(cur, admin)
    with pytest.raises(psycopg.errors.InvalidParameterValue, match="mapped more than once: lon"):
        cur.execute("select public.onboarding_decide(%s, 'approve')", (rid,))


def test_without_any_coordinates_lon_is_still_required(cur):
    admin = _user(cur, "admin")
    rid = _run(cur)
    cur.execute("reset role")
    cur.execute("update public.onboarding_mappings set unified_field = null where run_id = %s and source_col = 'Lat/Long'",
                (rid,))
    _as(cur, admin)
    with pytest.raises(psycopg.errors.InvalidParameterValue, match="required fields not mapped: lat, lon"):
        cur.execute("select public.onboarding_decide(%s, 'approve')", (rid,))


def test_a_non_admin_cannot_decide(cur):
    analyst = _user(cur, "analyst")
    rid = _run(cur)
    _as(cur, analyst)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("select public.onboarding_decide(%s, 'approve')", (rid,))
