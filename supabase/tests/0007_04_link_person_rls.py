"""Positive and RLS-negative checks for 0007_04 link_person against a live database.

Everything runs inside ONE transaction that is always ROLLED BACK, so nothing persists. The migration
file is applied inside that transaction too, so the test also works before the migration is live.
Uses the demo profiles from SETUP.md ("Demo users") and a console-filed Adyar case.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_04_link_person_rls.py

Exit code 1 when any check fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import db_migrate  # noqa: E402  (pooler connection, password from the environment)

MIGS = [Path(__file__).resolve().parents[1] / "migrations" / name
        for name in ("0007_04_link_person.sql", "0007_05_link_person_no_complexion.sql")]
ADYAR = "5a301b38-26e4-4614-90cc-42fe416eb61b"      # station_officer, PS-ADYAR-J2
VELACHERY = "2e4e8dbe-c796-4276-8581-49813f70a718"  # station_officer, PS-VELACHERY-J7
ANALYST = "92b32c25-0e5a-443f-831a-379cfd40874c"
CASE = "CHN-AD-2026-001231"                          # Adyar case

fails = 0


def as_user(cur, uid: str) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))
    cur.execute("set local role authenticated")


def call(cur, label: str, payload: dict, expect_ok: bool):
    global fails
    cur.execute("savepoint s")
    try:
        cur.execute("select public.link_person(%s::jsonb)", (json.dumps(payload),))
        result = cur.fetchone()[0]
        cur.execute("release savepoint s")
        ok = expect_ok
        print("PASS" if ok else "FAIL (allowed)", label, "->", result)
    except Exception as exc:  # noqa: BLE001 - the error text is the result
        cur.execute("rollback to savepoint s")
        result = None
        ok = not expect_ok
        print("PASS" if ok else "FAIL", label, "->", str(exc).splitlines()[0][:90])
    fails += 0 if ok else 1
    return result


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        for mig in MIGS:
            cur.execute(mig.read_text(encoding="utf8"))

        as_user(cur, ADYAR)
        accused = call(cur, "officer links a new named accused", {"crime_id": CASE, "role": "accused", "name": "Raju alias Pulsar Raju",
                       "aliases": ["Pulsar Raju"], "descriptors": {"build": "thin", "age_band": "20-30", "marks": "scar left cheek"}}, True)
        call(cur, "same person re-linked as suspect", {"crime_id": CASE, "role": "suspect", "person_id": accused}, True)
        call(cur, "described witness, no name", {"crime_id": CASE, "role": "witness", "descriptors": {"gender": "F", "age_band": "40-50"}}, True)
        call(cur, "witness with a name refused (J5)", {"crime_id": CASE, "role": "witness", "name": "Lakshmi"}, False)
        call(cur, "named person linked as victim refused (J5)", {"crime_id": CASE, "role": "victim", "person_id": accused}, False)
        call(cur, "unknown descriptor refused", {"crime_id": CASE, "role": "suspect", "descriptors": {"religion": "x"}}, False)
        call(cur, "complexion refused (LNK-13, 0007_05)", {"crime_id": CASE, "role": "suspect", "descriptors": {"complexion": "fair"}}, False)
        call(cur, "empty person refused", {"crime_id": CASE, "role": "suspect"}, False)
        call(cur, "bad role refused", {"crime_id": CASE, "role": "informer", "name": "x"}, False)

        cur.execute("reset role")
        cur.execute("select count(*), count(*) filter (where who = %s) from audit_log where what = 'link_person' and object_id = %s", (ADYAR, CASE))
        total, by_officer = cur.fetchone()
        check("every link is audited with the acting officer as who", total == 3 and by_officer == 3, f"({by_officer}/{total})")

        as_user(cur, VELACHERY)
        call(cur, "RLS-NEGATIVE other-station officer refused", {"crime_id": CASE, "role": "suspect", "person_id": accused}, False)
        as_user(cur, ANALYST)
        call(cur, "RLS-NEGATIVE analyst refused (cannot write cases)", {"crime_id": CASE, "role": "suspect", "person_id": accused}, False)
        cur.execute("savepoint d")
        try:
            cur.execute("insert into person_links (person_id, crime_id, role) values (%s, %s, 'accused')", (accused, CASE))
            check("RLS-NEGATIVE direct insert into person_links refused", False)
        except Exception:  # noqa: BLE001
            check("RLS-NEGATIVE direct insert into person_links refused", True)
        cur.execute("rollback to savepoint d")

        cur.execute("reset role")
        cur.execute("select has_function_privilege('anon', 'public.link_person(jsonb)', 'execute')")
        check("RLS-NEGATIVE anon cannot execute link_person", cur.fetchone()[0] is False)
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
