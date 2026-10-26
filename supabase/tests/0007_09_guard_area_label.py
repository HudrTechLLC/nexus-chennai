"""Checks for 0007_09: the appeal publish guard also checks area_label.

ONE transaction, always ROLLED BACK. Applies 0007_09 inside it (0007_08 is already live).

    NEXUS_DB_PASSWORD="$(tr -d '\r\n' < <password file>)" python supabase/tests/0007_09_guard_area_label.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import db_migrate  # noqa: E402

MIG = ROOT / "supabase" / "migrations" / "0007_09_guard_area_label.sql"
CASE = "CHN-AD-2024-001253"   # non-hero Adyar case, in no alert
PI = "PI-TEST-0709"
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def publish(cur, area: str):
    cur.execute("savepoint s")
    try:
        cur.execute("update public_incidents set area_label = %s, status = 'published', approved_by = 'test:0709' where public_incident_id = %s",
                    (area, PI))
        cur.execute("rollback to savepoint s")
        return None
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        return str(exc).splitlines()[0]


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))
        cur.execute("update crimes set address = 'near VHS Hospital, Adyar' where crime_id = %s", (CASE,))
        cur.execute("insert into persons (person_id, name, aliases, synthetic) values ('P-TEST-0709', 'B. Ashok', '{}', true)")
        cur.execute("insert into person_links (person_id, crime_id, role, synthetic) values ('P-TEST-0709', %s, 'accused', true)", (CASE,))
        cur.execute("""insert into public_incidents (public_incident_id, crime_id, title, category, area_label, cell, week, time_window, summary, status, synthetic)
                       values (%s, %s, 'Mobile snatching', 'robbery', 'Adyar', '88618c4f4bfffff', '2026-W34', 'Evening', 'A phone was snatched.', 'draft', true)""",
                    (PI, CASE))
        for area, kind in [("Adyar (near VHS Hospital, Adyar area)", "place from the case address"),
                           ("Adyar, near Ashok's shop", "person name from the case"),
                           ("PS-ADYAR-J2 limits", "internal id")]:
            err = publish(cur, area)
            check(f"blocks area {area!r}", bool(err) and kind in err, f"-> {err}")
        for area in ("Adyar", "Adyar (LB Road area)"):
            err = publish(cur, area)
            check(f"allows area {area!r}", err is None, f"-> {err}")
        cur.execute("savepoint s")
        try:
            cur.execute("update public_incidents set summary = 'Ashok was seen', status = 'published', approved_by = 'test:0709' where public_incident_id = %s", (PI,))
            check("summary check still in place", False)
        except Exception as exc:  # noqa: BLE001
            check("summary check still in place", "person name" in str(exc))
        cur.execute("rollback to savepoint s")
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
