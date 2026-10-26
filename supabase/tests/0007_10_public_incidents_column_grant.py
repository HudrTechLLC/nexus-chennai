"""Checks for 0007_10: officers may update only the appeal fields the console edits, and cannot insert appeals.

ONE transaction, always ROLLED BACK. Applies 0007_10 inside it and acts as the Adyar station officer
(request.jwt.claims + role authenticated) on a draft appeal for a non-hero Adyar case.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_10_public_incidents_column_grant.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import db_migrate  # noqa: E402

MIG = ROOT / "supabase" / "migrations" / "0007_10_public_incidents_column_grant.sql"
ADYAR = "5a301b38-26e4-4614-90cc-42fe416eb61b"  # station_officer, PS-ADYAR-J2
CASE = "CHN-AD-2024-001253"                     # non-hero Adyar case, in no alert
PI = "PI-TEST-0710"
R15 = "8f618c4f4b0a2c1"                        # a resolution-15 cell: an exact point
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def as_officer(cur) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": ADYAR, "role": "authenticated"}),))
    cur.execute("set local role authenticated")


def attempt(cur, sql: str, args: tuple):
    """Run as the officer; return (rowcount, error)."""
    cur.execute("savepoint s")
    try:
        as_officer(cur)
        cur.execute(sql, args)
        n = cur.rowcount
        cur.execute("release savepoint s")
        return n, None
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        return None, str(exc).splitlines()[0][:90]


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))
        cur.execute("""insert into public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week, time_window, summary, status, synthetic)
                       values (%s, %s, 'Mobile snatching', 'robbery', 'Adyar', '88618c4f4bfffff', '2026-W34', 'Evening', 'A phone was snatched.', 'draft', true)""",
                    (PI, CASE))

        upd = "update public_incidents set {} = %s where public_incident_id = %s"
        for col, val in [("title", "Mobile snatching in Adyar"), ("area_label", "Adyar"), ("summary", "Two riders took a phone."),
                         ("looking_for", ["A white scooter"]), ("images", "[]")]:
            n, err = attempt(cur, upd.format(col), (val, PI))
            check(f"officer may update {col}", n == 1 and err is None, f"-> {n} {err or ''}")
        for col, val in [("cell", R15), ("time_window", "Exactly 7:42 pm outside No. 12"), ("category", "x"), ("week", "2026-W01"),
                         ("crime_id", "CHN-AD-2024-001252"), ("approved_by", "someone"), ("published_at", "2026-01-01"), ("sanitiser_model", "x")]:
            n, err = attempt(cur, upd.format(col), (val, PI))
            check(f"RLS-NEGATIVE officer cannot update {col}", err is not None and "permission denied" in err, f"-> {err}")
        n, err = attempt(cur, """insert into public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week, time_window, summary, status)
                                 values ('PI-TEST-0710-B', %s, 't', 'robbery', 'Adyar', %s, '2026-W34', 'Evening', 's', 'draft')""", (CASE, R15))
        check("RLS-NEGATIVE officer cannot insert an appeal", err is not None and "permission denied" in err, f"-> {err}")

        n, err = attempt(cur, "update public_incidents set status = 'published' where public_incident_id = %s", (PI,))
        cur.execute("reset role")
        cur.execute("select status, approved_by, published_at is not null from public_incidents where public_incident_id = %s", (PI,))
        row = cur.fetchone()
        check("officer can still publish; the trigger still stamps approved_by and published_at",
              err is None and row == ("published", "station_officer:PS-ADYAR-J2", True), f"-> {err or row}")

        cur.execute("update public_incidents set cell = '88618c4f4bfffff' where public_incident_id = %s", (PI,))
        check("service role keeps full access", cur.rowcount == 1)
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
