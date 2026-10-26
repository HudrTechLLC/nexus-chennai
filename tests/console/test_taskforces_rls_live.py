"""Live RLS-negative checks for joint task forces (0004_06_03), inside a transaction that is rolled back.

Skipped unless NEXUS_DB_PASSWORD is set for the command, read from the password file:

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" pytest -q tests/console/test_taskforces_rls_live.py

Seeds a station, one crime and five users (analyst, supervisor, two station officers, one of them a
member) inside the transaction. If 0004_06_03 is not applied yet, the migration file is loaded inside
the same transaction, so the test also runs before the migration is applied. Nothing is committed.
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
MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "0004_06_03_taskforces.sql"
INVITES = MIGRATIONS / "0004_06_04_taskforce_invites.sql"


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
        c.execute("select to_regprocedure('public.taskforce_propose(text,text,text,text,text[])') is not null")
        if not c.fetchone()[0]:
            c.execute("set local search_path = public, extensions")
            c.execute(MIGRATION.read_text(encoding="utf-8"))
            c.execute("reset search_path")
        # 0004_06_04 is a plain create-or-replace, so loading it in the rolled-back transaction is always safe.
        c.execute(INVITES.read_text(encoding="utf-8"))
        yield c
        conn.rollback()


def _seed(cur) -> dict[str, str]:
    sfx = uuid.uuid4().hex[:6].upper()
    st = f"PS-TFTEST-{sfx}"
    cur.execute("insert into public.stations (station_id, name, type, synthetic) values (%s,'TF test','law_and_order',true)", (st,))
    users = {}
    for role, key in (("analyst", "analyst"), ("supervisor", "supervisor"), ("station_officer", "member"), ("station_officer", "outsider")):
        uid = str(uuid.uuid4())
        cur.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"tf-{key}-{sfx}@example.invalid"))
        cur.execute("insert into public.profiles (user_id, name, role, station_id) values (%s,%s,%s,%s)",
                    (uid, key, role, st if role == "station_officer" else None))
        users[key] = uid
    crime = f"CHN-TF-{sfx}"
    cur.execute(
        "insert into public.crimes (crime_id, station_id, fir_no, category, occurred_from, reported_at, lat, lon,"
        " severity, narrative, address, h3_r8, week, synthetic) values (%s,%s,'1/2026','robbery',now(),now(),"
        "13.0,80.25,3,'n','a','88abc','2026-W43',true)", (crime, st))
    users["crime"] = crime
    return users


def _as(cur, uid: str | None):
    """Switch to the authenticated role with this user's JWT claims (None = anon)."""
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


def _propose(cur, u) -> str:
    _as(cur, u["analyst"])
    cur.execute("select public.taskforce_propose('Test TF', 'why', null, null, %s)", ([u["crime"]],))
    return cur.fetchone()[0]


def test_anon_cannot_call_any_rpc(cur):
    u = _seed(cur)
    _as(cur, None)
    assert _refused(cur, "select public.taskforce_propose('x anon', null, null, null, null)")
    assert _refused(cur, "select public.taskforce_decide('TF-X', 'approve', null)")
    assert _refused(cur, "select public.taskforce_add_note('TF-X', 'hi')")
    assert _refused(cur, "select public.taskforce_set_member('TF-X', %s, 'member')", (u["analyst"],))
    assert _refused(cur, "select public.taskforce_link_cases('TF-X', %s)", ([u["crime"]],))


def test_station_officer_cannot_propose_or_decide(cur):
    u = _seed(cur)
    _as(cur, u["outsider"])
    assert _refused(cur, "select public.taskforce_propose('Officer TF', null, null, null, null)")
    tf = _propose(cur, u)
    _as(cur, u["outsider"])
    assert _refused(cur, "select public.taskforce_decide(%s, 'approve', null)", (tf,))


def test_analyst_cannot_decide_or_add_members(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    assert _refused(cur, "select public.taskforce_decide(%s, 'approve', null)", (tf,))
    assert _refused(cur, "select public.taskforce_set_member(%s, %s, 'member')", (tf, u["member"]))


def test_lifecycle_members_notes_and_audit(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    cur.execute("select status, created_by::text, synthetic from public.taskforces where taskforce_id = %s", (tf,))
    assert cur.fetchone() == ("proposed", u["analyst"], True)
    cur.execute("select count(*) from public.taskforce_cases where taskforce_id = %s", (tf,))
    assert cur.fetchone()[0] == 1

    _as(cur, u["supervisor"])
    cur.execute("select public.taskforce_decide(%s, 'approve', 'go')", (tf,))
    assert cur.fetchone()[0] == "active"
    cur.execute("select public.taskforce_set_member(%s, %s, 'member')", (tf, u["member"]))

    # a member may add a note, a non-member officer may not
    _as(cur, u["member"])
    cur.execute("select public.taskforce_add_note(%s, 'member note')", (tf,))
    _as(cur, u["outsider"])
    assert _refused(cur, "select public.taskforce_add_note(%s, 'sneaky')", (tf,))
    # a plain member may not link cases (leads and supervisors only)
    _as(cur, u["member"])
    assert _refused(cur, "select public.taskforce_link_cases(%s, %s)", (tf, [u["crime"]]))

    # every write left exactly one audit row, attributed to its caller
    cur.execute("reset role")
    cur.execute("select what, who::text from public.audit_log where object_type = 'taskforce' and object_id = %s order by audit_id", (tf,))
    assert cur.fetchall() == [("propose_taskforce", u["analyst"]), ("approve_taskforce", u["supervisor"]),
                              ("set_taskforce_member", u["supervisor"]), ("note_taskforce", u["member"])]

    # illegal transitions are refused
    _as(cur, u["supervisor"])
    assert _refused(cur, "select public.taskforce_decide(%s, 'approve', null)", (tf,))
    cur.execute("select public.taskforce_decide(%s, 'close', null)", (tf,))
    assert cur.fetchone()[0] == "closed"
    assert _refused(cur, "select public.taskforce_add_note(%s, 'after close')", (tf,))


def test_no_direct_writes_for_authenticated(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    _as(cur, u["supervisor"])
    assert _refused(cur, "insert into public.taskforces (taskforce_id, name, created_by) values ('TF-DIRECT','x',%s)", (u["supervisor"],))
    assert _refused(cur, "update public.taskforces set status = 'active' where taskforce_id = %s", (tf,))
    assert _refused(cur, "insert into public.taskforce_members (taskforce_id, user_id) values (%s, %s)", (tf, u["member"]))
    assert _refused(cur, "insert into public.taskforce_cases (taskforce_id, crime_id) values (%s, %s)", (tf, u["crime"]))
    assert _refused(cur, "insert into public.taskforce_notes (taskforce_id, author, text) values (%s, %s, 'x')", (tf, u["supervisor"]))


def test_notes_are_append_only_even_for_service_role(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    _as(cur, u["supervisor"])
    cur.execute("select public.taskforce_add_note(%s, 'keep me')", (tf,))
    note = cur.fetchone()[0]
    cur.execute("reset role")  # postgres: bypasses RLS, not triggers
    assert _refused(cur, "update public.taskforce_notes set text = 'changed' where note_id = %s", (note,))
    assert _refused(cur, "delete from public.taskforce_notes where note_id = %s", (note,))


def test_every_police_role_reads(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    for who in ("outsider", "member", "analyst", "supervisor"):
        _as(cur, u[who])
        cur.execute("select count(*) from public.taskforces where taskforce_id = %s", (tf,))
        assert cur.fetchone()[0] == 1, who
        cur.execute("select count(*) from public.taskforce_cases where taskforce_id = %s", (tf,))
        assert cur.fetchone()[0] == 1, who
    _as(cur, None)
    assert _refused(cur, "select count(*) from public.taskforces")


def test_adding_a_member_notifies_them_once(cur):
    u = _seed(cur)
    tf = _propose(cur, u)
    _as(cur, u["supervisor"])
    cur.execute("select public.taskforce_set_member(%s, %s, 'member')", (tf, u["member"]))
    cur.execute("select public.taskforce_set_member(%s, %s, 'lead')", (tf, u["member"]))  # role change: no second invite
    cur.execute("reset role")
    cur.execute("select kind, title, link from public.notifications where user_id = %s", (u["member"],))
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "taskforce_invite"
    assert rows[0][1] == "Invited to task force Test TF"
    assert rows[0][2] == f"/console/taskforces/{tf}"
    _as(cur, u["supervisor"])
    cur.execute("select public.taskforce_set_member(%s, %s, null)", (tf, u["member"]))  # removal: nothing new
    cur.execute("reset role")
    cur.execute("select count(*) from public.notifications where user_id = %s", (u["member"],))
    assert cur.fetchone()[0] == 1
