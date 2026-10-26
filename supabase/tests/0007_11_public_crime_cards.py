"""Checks for 0007_11: public per-crime cards and tips linked to a crime.

ONE transaction, always ROLLED BACK. Applies 0007_11 inside it, then calls the new RPCs as anon (and triage as an
admin) and checks:
  * grants: anon may call public_hex_crimes, public_crime and submit_tip only; the helpers and tables are closed;
  * cards hold only the allowed fields, obey the >=3 rule (cell AND category) and sort by week then public id;
  * public_crime round-trips a card id and returns null for anything else (including a raw crime id);
  * every MO sentence on every public card passes the appeal leak guard (appeal_case_leak) and has no digit;
  * submit_tip: old-style calls still work, p_about links the tip to the crime, an unknown id is refused;
  * tip_nearby_crimes lists the linked crime first.
Never touches a hero case (AD-001182, VL-000877, AD-001231): it picks other crimes.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python supabase/tests/0007_11_public_crime_cards.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import db_migrate  # noqa: E402

MIG = ROOT / "supabase" / "migrations" / "0007_11_public_crime_cards.sql"
HEROES = ("CHN-AD-2026-001182", "CHN-VL-2026-000877", "CHN-AD-2026-001231")
CARD_KEYS = {"public_id", "category", "sub_type", "week", "time_window", "cell", "area", "status", "in_pattern",
             "mo_summary", "appeals"}
fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global fails
    fails += 0 if ok else 1
    print("PASS" if ok else "FAIL", label, detail)


def as_anon(cur) -> None:
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"role": "anon"}),))
    cur.execute("set local role anon")


def raises(cur, sql: str, args: tuple) -> str | None:
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
        cur.execute("select count(*) from public_id_secret")
        check("secret: exactly one row after a replay", cur.fetchone()[0] == 1)

        # ----- grants -----
        for fn, want in [("public.public_hex_crimes(text, integer, text)", True), ("public.public_crime(text)", True),
                         ("public.submit_tip(text, text, text, text, boolean, text, text, jsonb, text, text)", True),
                         ("public.crime_public_id(text)", False), ("public.public_card_pool(integer)", False),
                         ("public.public_area_label(text)", False), ("public.public_mo_summary(text)", False),
                         ("public.public_crime_card(text, text)", False)]:
            cur.execute("select has_function_privilege('anon', %s, 'execute'), "
                        "has_function_privilege('authenticated', %s, 'execute')", (fn, fn))
            got = cur.fetchone()
            check(f"grant {fn} anon/auth={want}", got == (want, want), str(got))
        for t in ("public_id_secret", "public_mo_phrases"):
            cur.execute("select has_table_privilege('anon', %s, 'select'), has_table_privilege('authenticated', %s, 'select')",
                        (f"public.{t}", f"public.{t}"))
            check(f"RLS-NEGATIVE {t} unreadable by API roles", cur.fetchone() == (False, False))
        fns = ("crime_public_id", "public_card_pool", "public_area_label", "public_mo_summary", "public_crime_card",
               "public_hex_crimes", "public_crime", "submit_tip", "tip_nearby_crimes",
               "public_map_cells")  # 0007_13 (nexus-4) recreates it with the same pin
        cur.execute("""select proname, prosecdef, coalesce(array_to_string(proconfig, ';'), '') from pg_proc
                       where pronamespace = 'public'::regnamespace and proname = any(%s)""", (list(fns),))
        procs = cur.fetchall()
        check("search_path: every 0007_11 function pins public, pg_temp",
              len(procs) == len(fns) and all("search_path=public, pg_temp" in cfg for _, _, cfg in procs),
              str([(n, c) for n, _, c in procs if "search_path=public, pg_temp" not in c]))
        cur.execute("""select c.relrowsecurity, (select count(*) from pg_policies where schemaname = 'public'
                       and tablename = 'public_id_secret') from pg_class c where c.oid = 'public.public_id_secret'::regclass""")
        check("RLS-NEGATIVE public_id_secret: RLS on, no policies", cur.fetchone() == (True, 0))
        for role in ("anon", "authenticated"):
            cur.execute("""select bool_or(has_table_privilege(%s, 'public.public_id_secret', p))
                           from unnest(array['select', 'insert', 'update', 'delete', 'truncate', 'references']) p""", (role,))
            check(f"RLS-NEGATIVE public_id_secret: no privilege at all for {role}", cur.fetchone()[0] is False)
        cur.execute("select count(*) from pg_proc where proname = 'submit_tip' and pronamespace = 'public'::regnamespace")
        check("submit_tip: one overload only (no ambiguous calls)", cur.fetchone()[0] == 1)

        # ----- pick cells (as owner) -----
        cur.execute("""select cell, count(*) from public_card_pool(30) where crime_id <> all(%s)
                       group by cell order by count(*) desc, cell limit 1""", (list(HEROES),))
        cell, n_cell = cur.fetchone()
        cur.execute("select crime_id, category from public_card_pool(30) where cell = %s and crime_id <> all(%s) limit 1",
                    (cell, list(HEROES)))
        about_crime, about_cat = cur.fetchone()
        cur.execute("""with w as (select h3_r8 cell, count(*) n from crimes
                                  where h3_r8 is not null and occurred_from >= now() - interval '30 days' group by 1)
                       select cell from w where n between 1 and 2 limit 1""")
        small = cur.fetchone()
        cur.execute("""with w as (select h3_r8 cell, category, count(*) n from crimes
                                  where h3_r8 is not null and occurred_from >= now() - interval '30 days' group by 1, 2),
                            t as (select cell, sum(n) tot from w group by 1)
                       select w.cell, w.category from w join t using (cell) where t.tot >= 3 and w.n < 3 limit 1""")
        rare = cur.fetchone()

        # ----- public_hex_crimes as anon -----
        as_anon(cur)
        cur.execute("select public_hex_crimes(%s, 30, null)", (cell,))
        hx = cur.fetchone()[0]
        cards = hx["cards"]
        check("hex: cards for an eligible cell", len(cards) >= 3 and len(cards) <= n_cell + len(HEROES), f"{len(cards)} cards")
        check("hex: area label is a place name (no station code)", bool(hx["area"]) and "(" not in hx["area"], hx["area"])
        check("cards: only the allowed fields", all(set(c) == CARD_KEYS for c in cards))
        blob = json.dumps(cards)
        check("cards: no crime id or FIR number anywhere", "CHN-" not in blob and "fir" not in blob.lower())
        check("cards: public id shape", all(re.fullmatch(r"PC-[0-9A-F]{12}", c["public_id"]) for c in cards))
        check("cards: sorted by week desc then public id",
              [(c["week"], c["public_id"]) for c in cards] == sorted(((c["week"], c["public_id"]) for c in cards),
                                                                     key=lambda x: (tuple(-ord(ch) for ch in x[0]), x[1])))
        check("cards: plain status words", all(c["status"] in ("open", "charge-sheeted", "closed") for c in cards))
        check("cards: time window bands", all(c["time_window"] in ("morning", "afternoon", "evening", "night") for c in cards))
        if small:
            cur.execute("select public_hex_crimes(%s, 30, null)", small)
            r = cur.fetchone()[0]
            check("min-count: a hex under 3 shows no cards and no area", r["cards"] == [] and r["area"] is None)
        if rare:
            cur.execute("select public_hex_crimes(%s, 30, %s)", rare)
            check("min-count: a category under 3 in the hex shows no cards", cur.fetchone()[0]["cards"] == [])
            cur.execute("select public_hex_crimes(%s, 30, null)", (rare[0],))
            check("min-count: unfiltered hex never reveals the rare category",
                  all(c["category"] != rare[1] for c in cur.fetchone()[0]["cards"]))
        cur.execute("select public_hex_crimes('not-a-cell', 30, null)")
        check("hex: junk cell gives no cards", cur.fetchone()[0]["cards"] == [])

        # ----- public_crime -----
        pid = cards[0]["public_id"]
        cur.execute("select public_crime(%s)", (pid,))
        check("public_crime: round-trips a card id", cur.fetchone()[0] == cards[0])
        for bad in ("PC-000000000000", about_crime, "pc-" + pid[3:].lower(), "' or 1=1 --"):
            cur.execute("select public_crime(%s)", (bad,))
            check(f"public_crime: null for {bad[:20]!r}", cur.fetchone()[0] is None)
        check("RLS-NEGATIVE anon cannot call crime_public_id",
              raises(cur, "select crime_public_id(%s)", (about_crime,)) is not None)

        # ----- leak guard over every public MO sentence (owner role: appeal_case_leak is not for API roles) -----
        cur.execute("reset role")
        cur.execute("""select p.crime_id, public_mo_summary(p.crime_id) from public_card_pool(90) p""")
        rows = [(c, s) for c, s in cur.fetchall() if s]
        leaks = []
        for c, s in rows:
            cur.execute("select appeal_case_leak(%s, %s)", (c, s))
            k = cur.fetchone()[0]
            if k or re.search(r"\d", s):
                leaks.append((c, s, k))
        check("MO sentences: leak guard clean and no digits", not leaks, f"{len(rows)} sentences; {leaks[:3]}")
        cur.execute("select public_mo_summary(crime_id) from crime_features where (mo ->> 'approach') = 'two_wheeler_from_behind' limit 1")
        print("     sample:", cur.fetchone()[0])

        # ----- submit_tip as anon -----
        cur.execute("select crime_public_id(%s)", (about_crime,))
        about_pid = cur.fetchone()[0]
        as_anon(cur)
        cur.execute("""select submit_tip(p_appeal => null, p_category => 'something_else', p_text => 'test 0711 old style',
                       p_cell => null, p_follow_up => false, p_code => null, p_passphrase => null, p_media => '[]'::jsonb,
                       p_tz => 'Asia/Kolkata')""")
        old = cur.fetchone()[0]
        check("submit_tip: old-style call (no p_about) still works", bool(old.get("tip_id")))
        cur.execute("""select submit_tip(p_appeal => null, p_category => 'something_else', p_text => 'test 0711 follow-up',
                       p_cell => null, p_follow_up => true, p_code => 'TESTAB23', p_passphrase => 'correct horse 0711',
                       p_media => '[]'::jsonb, p_tz => 'Asia/Kolkata')""")
        check("submit_tip: follow-up tip (bcrypt via extensions.crypt) works", cur.fetchone()[0]["tip_id"] == "TIP-TESTAB23")
        cur.execute("""select submit_tip(p_appeal => null, p_category => 'something_else', p_text => 'test 0711 about',
                       p_cell => %s, p_follow_up => false, p_code => null, p_passphrase => null, p_media => '[]'::jsonb,
                       p_tz => 'Asia/Kolkata', p_about => %s)""", (cell, about_pid))
        tip = cur.fetchone()[0]["tip_id"]
        err = raises(cur, """select submit_tip(p_appeal => null, p_category => 'something_else', p_text => 'x about',
                       p_cell => null, p_follow_up => false, p_code => null, p_passphrase => null, p_media => '[]'::jsonb,
                       p_tz => 'Asia/Kolkata', p_about => %s)""", (about_crime,))
        check("submit_tip: a raw crime id as p_about is refused", bool(err) and "unknown crime" in err, str(err))
        cur.execute("reset role")
        cur.execute("select about_crime_id from tips where tip_id = %s", (tip,))
        check("submit_tip: tip linked to the crime server-side", cur.fetchone()[0] == about_crime)

        # ----- triage lists the linked crime first (as an admin) -----
        cur.execute("select user_id from profiles where role = 'admin' limit 1")
        admin = str(cur.fetchone()[0])
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": admin, "role": "authenticated"}),))
        cur.execute("set local role authenticated")
        cur.execute("select tip_nearby_crimes(%s)", (tip,))
        near = cur.fetchone()[0]
        check("triage: the crime the tip is about comes first",
              bool(near) and near[0]["crime_id"] == about_crime and near[0]["from_about"] is True)
    conn.rollback()

print("ROLLED BACK.", "ALL PASS" if not fails else f"{fails} FAIL")
sys.exit(1 if fails else 0)
