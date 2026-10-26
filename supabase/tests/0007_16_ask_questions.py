"""Checks for 0007_16: Ask Nexus question rows (WS3-30).

ONE transaction, always ROLLED BACK. Applies 0007_16 twice inside it (replayable), then acts as real profiles:
  * anon: no access at all; a station officer cannot ask or read;
  * an analyst can ask (only `question`), reads their own rows only, cannot set status/answer, update or delete;
  * a supervisor (second asker) cannot read the first one's question;
  * at most 3 unanswered questions per user; an answered one frees a slot;
  * the guard function is not callable by API roles and pins its search_path;
  * question length is checked.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_16_ask_questions.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import db_migrate  # noqa: E402

MIG = ROOT / "supabase" / "migrations" / "0007_16_ask_questions.sql"
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def act_as(cur, uid: str | None) -> None:
    cur.execute("reset role")
    if uid is None:
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
        cur.execute("set local role anon")
    else:
        cur.execute("select set_config('request.jwt.claims', %s, true)",
                    (json.dumps({"sub": uid, "role": "authenticated"}),))
        cur.execute("set local role authenticated")


def attempt(cur, sql: str, args: tuple = ()) -> str | None:
    cur.execute("savepoint s")
    try:
        cur.execute(sql, args)
        cur.execute("release savepoint s")
        return None
    except Exception as exc:  # noqa: BLE001
        cur.execute("rollback to savepoint s")
        return str(exc).splitlines()[0]


with db_migrate.connect() as conn:
    with conn.cursor() as cur:
        cur.execute(MIG.read_text(encoding="utf8"))
        cur.execute(MIG.read_text(encoding="utf8"))  # replayable

        cur.execute("(select user_id from profiles where role = 'analyst' order by user_id limit 1) union all "
                    "(select user_id from profiles where role = 'supervisor' order by user_id limit 1)")
        analysts = [r[0] for r in cur.fetchall()]
        cur.execute("select user_id from profiles where role = 'station_officer' order by user_id limit 1")
        officer = cur.fetchone()[0]
        check("fixtures: an analyst, a supervisor and an officer", len(analysts) == 2)
        a1, a2 = (str(x) for x in analysts)

        # ----- grants -----
        fn = "public.ask_questions_guard()"
        cur.execute("select has_function_privilege('anon', %s, 'execute'), "
                    "has_function_privilege('authenticated', %s, 'execute')", (fn, fn))
        check("guard not callable by API roles", cur.fetchone() == (False, False))
        cur.execute("select proconfig from pg_proc where proname = 'ask_questions_guard'")
        check("guard pins search_path = public, pg_temp", cur.fetchone()[0] == ["search_path=public, pg_temp"])
        for priv in ("update", "delete"):
            cur.execute("select has_table_privilege('authenticated', 'public.ask_questions', %s)", (priv,))
            check(f"authenticated has no {priv}", cur.fetchone()[0] is False)
        cur.execute("select has_column_privilege('authenticated', 'public.ask_questions', 'status', 'insert'), "
                    "has_column_privilege('authenticated', 'public.ask_questions', 'question', 'insert')")
        check("insert grant covers question only", cur.fetchone() == (False, True))

        # ----- anon and officer -----
        act_as(cur, None)
        check("RLS-NEGATIVE anon cannot read", attempt(cur, "select count(*) from ask_questions") is not None)
        check("RLS-NEGATIVE anon cannot ask",
              attempt(cur, "insert into ask_questions (question) values ('robberies in Adyar')") is not None)
        act_as(cur, str(officer))
        check("RLS-NEGATIVE officer cannot ask",
              attempt(cur, "insert into ask_questions (question) values ('robberies in Adyar')") is not None)

        # ----- analyst asks -----
        act_as(cur, a1)
        err = attempt(cur, "insert into ask_questions (question) values ('house breaks in Adyar after 7 pm')")
        check("analyst can ask", err is None, err or "")
        cur.execute("select question_id, status, asked_by::text from ask_questions")
        mine = cur.fetchall()
        check("analyst reads own question, queued, asked_by = self",
              len(mine) == 1 and mine[0][1] == "queued" and mine[0][2] == a1, str(mine))
        qid = mine[0][0]
        check("RLS-NEGATIVE analyst cannot set status on insert",
              attempt(cur, "insert into ask_questions (question, status) values ('x y z', 'answered')") is not None)
        check("RLS-NEGATIVE analyst cannot write an answer",
              attempt(cur, "update ask_questions set answer = '{}'::jsonb where question_id = %s", (qid,)) is not None)
        check("RLS-NEGATIVE analyst cannot delete",
              attempt(cur, "delete from ask_questions where question_id = %s", (qid,)) is not None)
        check("too-short question refused",
              attempt(cur, "insert into ask_questions (question) values ('hi')") is not None)
        check("too-long question refused",
              attempt(cur, "insert into ask_questions (question) values (%s)", ("x" * 301,)) is not None)

        # ----- another asker (a supervisor) -----
        act_as(cur, a2)
        cur.execute("select count(*) from ask_questions where question_id = %s", (qid,))
        check("RLS-NEGATIVE another user (supervisor) cannot read it", cur.fetchone()[0] == 0)

        # ----- 3 in flight -----
        act_as(cur, a1)
        for q in ("robberies in Velachery", "thefts in Guindy"):
            attempt(cur, "insert into ask_questions (question) values (%s)", (q,))
        err = attempt(cur, "insert into ask_questions (question) values ('a fourth question')")
        check("4th unanswered question refused", err is not None and "3 questions" in err, err or "")
        cur.execute("reset role")
        cur.execute("update ask_questions set status = 'answered' where question_id = %s", (qid,))
        act_as(cur, a1)
        err = attempt(cur, "insert into ask_questions (question) values ('a fourth question')")
        check("an answered question frees a slot", err is None, err or "")

        # ----- the worker's write path: service_role sets status, plan and answer -----
        cur.execute("reset role")
        cur.execute("set local role service_role")
        err = attempt(cur, "update ask_questions set status = 'answered', plan = '{\"steps\": []}'::jsonb, "
                           "answer = '{\"rows\": []}'::jsonb, answered_at = now() where question_id = %s", (qid,))
        check("service_role (worker) can write status, plan and answer", err is None, err or "")

        cur.execute("reset role")
        conn.rollback()

print(f"\n{'ALL PASS' if fails == 0 else f'{fails} FAILED'} (rolled back)")
sys.exit(1 if fails else 0)
