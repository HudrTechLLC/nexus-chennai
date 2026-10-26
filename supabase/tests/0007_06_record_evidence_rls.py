"""Positive and RLS-negative checks for 0007_06 record_evidence + the case_diary author trigger.

Runs inside ONE transaction that is always ROLLED BACK (nothing persists). The migration is applied
inside it, and stand-in storage.objects rows are inserted there to play the part of uploads, so
no real file is created.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_06_record_evidence_rls.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import db_migrate  # noqa: E402

MIG = Path(__file__).resolve().parents[1] / "migrations" / "0007_06_record_evidence.sql"
ADYAR = "5a301b38-26e4-4614-90cc-42fe416eb61b"      # station_officer, PS-ADYAR-J2
VELACHERY = "2e4e8dbe-c796-4276-8581-49813f70a718"  # station_officer, PS-VELACHERY-J7
CASE = "CHN-AD-2026-001231"
SHA = "a" * 64
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def as_user(cur, uid: str) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": uid, "role": "authenticated"}),))
    cur.execute("set local role authenticated")


def fake_upload(cur, owner: str, ext: str, mime: str, size: int) -> str:
    """A storage.objects row as Storage writes it on upload (owner_id = uploader)."""
    path = f"{CASE}/{uuid.uuid4()}.{ext}"
    cur.execute("reset role")
    cur.execute("insert into storage.objects (bucket_id, name, owner, owner_id, metadata) values ('evidence', %s, %s, %s, %s)",
                (path, owner, owner, json.dumps({"size": size, "mimetype": mime})))
    return path


def rpc(cur, label: str, payload: dict, expect_ok: bool):
    cur.execute("savepoint s")
    try:
        cur.execute("select public.record_evidence(%s::jsonb)", (json.dumps(payload),))
        out = cur.fetchone()[0]
        cur.execute("release savepoint s")
        check(label, expect_ok, f"-> {out}")
        return out
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        check(label, not expect_ok, "-> " + str(exc).splitlines()[0][:90])
        return None


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))

        photo = fake_upload(cur, ADYAR, "jpg", "image/jpeg", 9885)
        audio = fake_upload(cur, ADYAR, "wav", "audio/wav", 3244)
        other = fake_upload(cur, VELACHERY, "jpg", "image/jpeg", 100)

        as_user(cur, ADYAR)
        ev = rpc(cur, "own upload recorded as evidence", {"crime_id": CASE, "path": photo, "sha256": SHA, "kind": "photo", "bytes": 9885,
                                                            "captured_at": "2026-10-20T14:14:12Z"}, True)
        st = rpc(cur, "own audio upload recorded as statement", {"crime_id": CASE, "path": audio, "sha256": SHA, "target": "statement"}, True)
        rpc(cur, "same path twice refused", {"crime_id": CASE, "path": photo, "sha256": SHA, "kind": "photo"}, False)
        rpc(cur, "someone else's upload refused", {"crime_id": CASE, "path": other, "sha256": SHA, "kind": "photo"}, False)
        rpc(cur, "path with no object refused", {"crime_id": CASE, "path": f"{CASE}/{uuid.uuid4()}.jpg", "sha256": SHA, "kind": "photo"}, False)
        rpc(cur, "size mismatch refused", {"crime_id": CASE, "path": fake_upload(cur, ADYAR, "jpg", "image/jpeg", 10), "sha256": SHA, "kind": "photo", "bytes": 11}, False)
        as_user(cur, ADYAR)
        rpc(cur, "kind/mime mismatch refused", {"crime_id": CASE, "path": fake_upload(cur, ADYAR, "wav", "audio/wav", 10), "sha256": SHA, "kind": "photo"}, False)
        as_user(cur, ADYAR)
        rpc(cur, "bad sha256 refused", {"crime_id": CASE, "path": fake_upload(cur, ADYAR, "jpg", "image/jpeg", 10), "sha256": "abc", "kind": "photo"}, False)

        cur.execute("reset role")
        cur.execute("select uploaded_by, custody->0->>'by', (custody->0->>'bytes')::int, custody->0->>'mime' from evidence_media where evidence_id = %s", (ev,))
        row = cur.fetchone()
        check("uploaded_by + custody set by the database from the session and storage", row == (ADYAR, ADYAR, 9885, "image/jpeg"), str(row))
        cur.execute("select witness_ref, mode from statements where statement_id = %s", (st,))
        check("audio statement gets a masked witness ref", (cur.fetchone() or ("", ""))[1] == "audio")
        cur.execute("select count(*) from audit_log where object_id = %s and what in ('add_evidence', 'add_audio_statement') and who = %s and details->>'path' in (%s, %s)",
                    (CASE, ADYAR, photo, audio))
        check("both recorded in audit_log with the officer as who", cur.fetchone()[0] == 2)

        as_user(cur, ADYAR)
        for table, cols in (("evidence_media", "(evidence_id, crime_id, kind, storage_path, sha256, uploaded_by) values ('EV-x', %s, 'photo', 'p', 'h', 'me')"),
                            ("statements", "(statement_id, crime_id, witness_ref, mode, text, recorded_at) values ('ST-x', %s, 'W', 'text', 't', now())")):
            cur.execute("savepoint d")
            try:
                cur.execute(f"insert into {table} {cols}", (CASE,))
                check(f"RLS-NEGATIVE direct insert into {table} refused", False)
            except Exception:  # noqa: BLE001
                check(f"RLS-NEGATIVE direct insert into {table} refused", True)
            cur.execute("rollback to savepoint d")

        as_user(cur, VELACHERY)
        rpc(cur, "RLS-NEGATIVE other-station officer refused (own upload, other case)", {"crime_id": CASE, "path": other, "sha256": SHA, "kind": "photo"}, False)

        as_user(cur, ADYAR)
        cur.execute("insert into case_diary (entry_id, crime_id, at, kind, text, author) values ('CD-x', %s, now(), 'lead', 'x', 'Someone Else') returning author", (CASE,))
        author = cur.fetchone()[0]
        check("case_diary author comes from the session, not the client", author == "Demo Station Officer", f"({author})")

        cur.execute("reset role")
        cur.execute("select has_function_privilege('anon', 'public.record_evidence(jsonb)', 'execute')")
        check("RLS-NEGATIVE anon cannot execute record_evidence", cur.fetchone()[0] is False)
    conn.rollback()

print("ROLLED BACK -", "ALL PASS" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
