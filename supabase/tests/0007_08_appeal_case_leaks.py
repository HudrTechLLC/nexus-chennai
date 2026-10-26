"""Checks for 0007_08: the appeal publish guard blocks names of people in the case and its address.

ONE transaction, always ROLLED BACK. Applies 0007_08 inside it, then gives a non-hero case the fixture's
persons and address (tests/agents/appeal_leaks.json → case_leaks) and runs every fixture text through the
real trigger by publishing a draft appeal. The same fixture drives pytest and vitest.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_08_appeal_case_leaks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import db_migrate  # noqa: E402

MIG = ROOT / "supabase" / "migrations" / "0007_08_appeal_case_leaks.sql"
FIX = json.loads((ROOT / "tests" / "agents" / "appeal_leaks.json").read_text("utf-8"))
CL = FIX["case_leaks"]
CASE = "CHN-AD-2024-001253"   # non-hero Adyar case, in no alert
PI = "PI-TEST-0708"
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def publish(cur, summary: str):
    """Publish the draft with this summary as the service path (approved_by supplied); return the error or None."""
    cur.execute("savepoint s")
    try:
        cur.execute("update public_incidents set summary = %s, status = 'published', approved_by = 'test:0708' where public_incident_id = %s",
                    (summary, PI))
        cur.execute("rollback to savepoint s")  # keep the draft a draft for the next text
        return None
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        return str(exc).splitlines()[0]


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))
        cur.execute("update crimes set address = %s where crime_id = %s", (CL["address"], CASE))
        for i, p in enumerate(CL["persons"]):
            pid = f"P-TEST-0708-{i}"
            cur.execute("insert into persons (person_id, name, aliases, synthetic) values (%s, %s, %s, true)", (pid, p["name"], p["aliases"]))
            cur.execute("insert into person_links (person_id, crime_id, role, synthetic) values (%s, %s, 'accused', true)", (pid, CASE))
        cur.execute("""insert into public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week, time_window, summary, status, synthetic)
                       values (%s, %s, 'Day house break', 'house_break', 'Vadapalani', '8861892b3ffffff', '2026-W43', 'Afternoon', 'x', 'draft', true)""", (PI, CASE))

        for c in CL["leaky"]:
            err = publish(cur, c["text"])
            check(f"blocks: {c['text']!r}", bool(err) and c["kind"] in err, f"-> {err}")
        for t in CL["clean"]:
            err = publish(cur, t)
            check(f"allows: {t!r}", err is None, f"-> {err}")
        for extra in CL["more_addresses"]:
            cur.execute("update crimes set address = %s where crime_id = %s", (extra["address"], CASE))
            cur.execute("delete from person_links where crime_id = %s and person_id like 'P-TEST-0708-%%'", (CASE,))
            for t in extra["leaky"]:
                err = publish(cur, t)
                check(f"blocks ({extra['address']}): {t!r}", bool(err) and "place from the case address" in err, f"-> {err}")
            for t in extra["clean"]:
                err = publish(cur, t)
                check(f"allows ({extra['address']}): {t!r}", err is None, f"-> {err}")
        for c in FIX["leaky"][:2]:
            err = publish(cur, c["text"])
            check(f"pattern guard unchanged: {c['kind']}", bool(err) and c["kind"] in err, f"-> {err}")

        cur.execute("savepoint s")
        cur.execute("update public_incidents set summary = 'Karthik was seen', status = 'draft' where public_incident_id = %s", (PI,))
        check("drafts are not checked (only publishing is)", cur.rowcount == 1)
        cur.execute("rollback to savepoint s")

        for fn in ("public.appeal_case_terms(text)", "public.appeal_case_leak(text, text)"):
            cur.execute("select has_function_privilege('authenticated', %s, 'execute'), has_function_privilege('anon', %s, 'execute')", (fn, fn))
            check(f"RLS-NEGATIVE {fn} not callable by API roles (no name oracle)", cur.fetchone() == (False, False))
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
