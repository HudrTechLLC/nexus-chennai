"""Checks for 0007_07 (link_alerts.weights_version + captured_from in the evidence audit).

ONE transaction, always ROLLED BACK. Applies 0007_07 inside it; stand-in storage.objects rows play uploads.

    NEXUS_DB_PASSWORD="$(tr -d '\r\n' < <password file>)" python supabase/tests/0007_07_weights_version_captured_from.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import db_migrate  # noqa: E402

MIG = Path(__file__).resolve().parents[1] / "migrations" / "0007_07_weights_version_captured_from.sql"
ADYAR = "5a301b38-26e4-4614-90cc-42fe416eb61b"  # station_officer, PS-ADYAR-J2
CASE = "CHN-AD-2024-001252"                     # non-hero Adyar case
SHA = "b" * 64
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def upload(cur) -> str:
    path = f"{CASE}/{uuid.uuid4()}.jpg"
    cur.execute("reset role")
    cur.execute("insert into storage.objects (bucket_id, name, owner, owner_id, metadata) values ('evidence', %s, %s, %s, %s)",
                (path, ADYAR, ADYAR, json.dumps({"size": 10, "mimetype": "image/jpeg"})))
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": ADYAR, "role": "authenticated"}),))
    cur.execute("set local role authenticated")
    return path


def record(cur, payload: dict):
    cur.execute("savepoint s")
    try:
        cur.execute("select public.record_evidence(%s::jsonb)", (json.dumps(payload),))
        cur.execute("release savepoint s")
        return True, ""
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        return False, str(exc).splitlines()[0][:80]


def audit_from(cur, path: str):
    cur.execute("reset role")
    cur.execute("select details ? 'captured_from', details->>'captured_from' from audit_log where what = 'add_evidence' and details->>'path' = %s", (path,))
    return cur.fetchone()


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))

        cur.execute("select is_nullable, data_type, column_default from information_schema.columns where table_schema = 'public' and table_name = 'link_alerts' and column_name = 'weights_version'")
        check("weights_version is a nullable text column with no default", cur.fetchone() == ("YES", "text", None))
        cur.execute("select count(*) filter (where weights_version is not null) from link_alerts")
        check("existing alerts stay NULL (pre-versioning)", cur.fetchone()[0] == 0)

        for src in ("exif", "officer"):
            p = upload(cur)
            ok, err = record(cur, {"crime_id": CASE, "path": p, "sha256": SHA, "kind": "photo", "captured_at": "2026-10-20T14:14:12Z", "captured_from": src})
            check(f"captured_from={src} recorded in audit details", ok and audit_from(cur, p) == (True, src), err)
        p = upload(cur)
        ok, err = record(cur, {"crime_id": CASE, "path": p, "sha256": SHA, "kind": "photo"})
        check("no captured_from -> key absent, still recorded", ok and audit_from(cur, p) == (False, None), err)
        p = upload(cur)
        ok, err = record(cur, {"crime_id": CASE, "path": p, "sha256": SHA, "kind": "photo", "captured_from": "gps"})
        check("unknown captured_from refused", not ok, err)

        cur.execute("reset role")
        cur.execute("select has_function_privilege('anon', 'public.record_evidence(jsonb)', 'execute'), has_function_privilege('authenticated', 'public.record_evidence(jsonb)', 'execute'), has_table_privilege('authenticated', 'public.evidence_media', 'insert')")
        check("grants unchanged (anon no, authenticated yes, no direct insert)", cur.fetchone() == (False, True, False))
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
