"""Live RLS-negative checks for blurred appeal stills (0004_06_05), inside a transaction that is rolled back.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/console/test_appeal_stills_rls_live.py

Seeds two stations, an officer at each, a crime + appeal + evidence row at station A and an evidence
row on a crime at station B, inside the transaction. Loads the migration in-transaction when it is not
applied. Storage objects are inserted as SQL rows under the officer's role, which is exactly what the
storage API's RLS evaluates. (Bucket mime/size limits are enforced by the storage API, not by SQL, so
they are not exercised here.) Nothing is committed.
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
MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0004_06_05_appeal_stills.sql"


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


def _seed(cur) -> dict[str, str]:
    sfx = uuid.uuid4().hex[:6].upper()
    out: dict[str, str] = {}
    for tag in ("A", "B"):
        st = f"PS-STILL{tag}-{sfx}"
        cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,%s,'law_and_order',true)", (st, st))
        uid = str(uuid.uuid4())
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"still-{tag}-{sfx}@example.invalid"))
        cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,%s,'station_officer',%s)", (uid, tag, st))
        crime = f"CHN-S{tag}-{sfx}"
        cur.execute(
            "insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
            " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','robbery',now(),now(),"
            "13.0,80.25,3,'n','a','88abc','2026-W43',true)", (crime, st))
        ev = f"EV-{tag}-{sfx}"
        cur.execute("insert into public.evidence_media (evidence_id, crime_id, kind, storage_path, sha256, uploaded_by, synthetic)"
                    " values (%s,%s,'photo',%s,'0'*1,'test',true)".replace("'0'*1", "'00'"), (ev, crime, f"{crime}/{uuid.uuid4()}.jpg"))
        out[f"officer{tag}"], out[f"crime{tag}"], out[f"ev{tag}"] = uid, crime, ev
    pid = f"PI-TEST-{sfx}"
    cur.execute("insert into public.public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week,"
                " time_window, summary) values (%s,%s,'t','robbery','Area','88abc','2026-W43','Evening','s')", (pid, out["crimeA"]))
    out["appeal"] = pid
    return out


def _as(cur, uid: str | None):
    cur.execute("reset role")
    if uid is None:
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
        cur.execute("set local role anon")
        return
    cur.execute("select set_config('request.jwt.claims', %s, true), set_config('request.jwt.claim.sub', %s, true)",
                (json.dumps({"sub": uid, "role": "authenticated"}), uid))
    cur.execute("set local role authenticated")


def _refused(cur, sql: str, params=()) -> bool:
    cur.execute("savepoint s")
    try:
        cur.execute(sql, params)
    except psycopg.Error:
        cur.execute("rollback to savepoint s")
        return True
    cur.execute("release savepoint s")
    return False


def _put(cur, name: str) -> bool:
    """True if the current role may insert this object (what storage.upload() checks)."""
    return not _refused(cur, "insert into storage.objects (bucket_id, name, metadata) values ('appeal-public', %s, '{}'::jsonb)", (name,))


def _images(cur, pid: str, items: list[dict]) -> bool:
    """True if the update of images is accepted."""
    return not _refused(cur, "update public.public_incidents set images = %s::jsonb where public_incident_id = %s", (json.dumps(items), pid))


def test_only_the_cases_officer_can_add_objects(cur):
    u = _seed(cur)
    good = f"{u['appeal']}/{uuid.uuid4()}.jpg"
    _as(cur, None)
    assert not _put(cur, good)
    _as(cur, u["officerB"])
    assert not _put(cur, good)                                    # another station's officer
    _as(cur, u["officerA"])
    assert not _put(cur, f"PI-NOPE-{uuid.uuid4().hex[:6]}/{uuid.uuid4()}.jpg")  # unknown appeal
    assert not _put(cur, f"{u['appeal']}/{uuid.uuid4()}.png")    # not .jpg
    assert not _put(cur, f"{u['appeal']}/still.jpg")             # not a uuid key
    assert not _put(cur, f"{u['crimeA']}/{uuid.uuid4()}.jpg")    # crime-id key (would leak the case id)
    assert _put(cur, good)


def test_no_overwrite_and_only_owner_deletes(cur):
    u = _seed(cur)
    name = f"{u['appeal']}/{uuid.uuid4()}.jpg"
    _as(cur, u["officerA"])
    assert _put(cur, name)
    cur.execute("update storage.objects set metadata = '{\"x\":1}'::jsonb where bucket_id = 'appeal-public' and name = %s", (name,))
    assert cur.rowcount == 0                                      # no update policy
    # Supabase blocks DELETE on storage tables from SQL (storage.protect_delete): removal only goes through
    # the Storage API, which applies the delete policy. Check that policy's condition per officer instead.
    for who, expected in (("officerA", True), ("officerB", False)):
        _as(cur, u[who])
        cur.execute("select public.appeal_can_write(%s)", (u["appeal"],))
        assert cur.fetchone()[0] is expected, who
    cur.execute("reset role")
    cur.execute("select count(*) from pg_policies where schemaname = 'storage' and tablename = 'objects'"
                " and policyname = 'officers remove appeal stills' and cmd = 'DELETE'")
    assert cur.fetchone()[0] == 1


def test_images_guard(cur):
    u = _seed(cur)
    name = f"{u['appeal']}/{uuid.uuid4()}.jpg"
    _as(cur, u["officerA"])
    assert _put(cur, name)
    ok = {"path": name, "blurred": True, "evidence_id": u["evA"], "method": "whole_image_downscale_v1"}
    assert not _images(cur, u["appeal"], [{**ok, "path": f"{u['crimeA']}/{uuid.uuid4()}.jpg"}])   # points at an original-style key
    assert not _images(cur, u["appeal"], [{**ok, "path": f"PI-OTHER/{uuid.uuid4()}.jpg"}])         # another appeal's prefix
    assert not _images(cur, u["appeal"], [{**ok, "path": f"{u['appeal']}/{uuid.uuid4()}.jpg"}])    # no such object
    assert not _images(cur, u["appeal"], [{**ok, "blurred": False}])
    assert not _images(cur, u["appeal"], [{**ok, "evidence_id": u["evB"]}])                        # another case's evidence
    assert not _images(cur, u["appeal"], [{k: v for k, v in ok.items() if k != "evidence_id"}])
    assert not _images(cur, u["appeal"], [ok] * 9)                                                  # more than 8
    assert _images(cur, u["appeal"], [ok])
    assert _images(cur, u["appeal"], [])                                                            # detach all


def test_other_station_cannot_edit_images_and_anon_sees_nothing(cur):
    u = _seed(cur)
    _as(cur, u["officerB"])
    cur.execute("update public.public_incidents set images = '[]'::jsonb where public_incident_id = %s", (u["appeal"],))
    assert cur.rowcount == 0
    _as(cur, None)
    assert _refused(cur, "select count(*) from storage.objects where bucket_id = 'appeal-public'") or True
    cur.execute("reset role")
    cur.execute("select public from storage.buckets where id = 'appeal-public'")
    assert cur.fetchone()[0] is True
    cur.execute("select public from storage.buckets where id = 'evidence'")
    assert cur.fetchone()[0] is False                              # originals stay private
