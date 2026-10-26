"""Unit tests for Ask Nexus (app.ask, app.ask_worker): the model's plan is checked and resolved in code, only
allow-listed named queries run, filters apply in code, test FIRs are excluded (D-033), the answer is templated, and
the worker claims each question once and frees stuck ones."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import pytest

from app.ask import (DEFAULT_DAYS, QUERY_LIMIT, STATIONS, Unmappable, answer_question, in_hours, resolve_plan,
                     resolve_time, understood)
from app.ask_worker import AskWorker

TODAY = date(2026, 10, 27)


def plan(**kw: Any) -> dict[str, Any]:
    return {"answerable": True, "category": None, "sub_type": None, "stations": [], "status": None, "time": None,
            "hours": None, "words": [], **kw}


# =====================
# Plan checks (code, not the model)
# =====================


class TestResolvePlan:
    def test_sub_type_implies_its_category(self):
        p = resolve_plan(plan(sub_type="chain_snatching"), TODAY)
        assert (p.category, p.sub_type) == ("robbery", "chain_snatching")

    def test_the_sub_type_decides_the_category_when_the_model_slips(self):
        # live, 27 Oct: Lightning sent category "theft" with sub_type "chain_snatching"
        p = resolve_plan(plan(category="theft", sub_type="chain_snatching"), TODAY)
        assert (p.category, p.sub_type) == ("robbery", "chain_snatching")

    @pytest.mark.parametrize("field,value", [("category", "piracy"), ("sub_type", "bank_heist"),
                                             ("status", "solved_by_magic")])
    def test_unknown_vocabulary_is_unmappable_never_dropped(self, field, value):
        with pytest.raises(Unmappable):
            resolve_plan(plan(**{field: value, "category": "robbery"} if field != "category" else {field: value}),
                         TODAY)

    def test_station_names_resolve_to_ids_from_the_city_pack(self):
        p = resolve_plan(plan(category="robbery", stations=["Adyar", "anna nagar"]), TODAY)
        assert [sid for sid, _ in p.stations] == ["PS-ADYAR-J2", "PS-ANNANAGAR-K4"]

    def test_a_sub_type_the_question_does_not_name_is_not_used(self):
        # live, 27 Oct: "Robberies mentioning a red Pulsar" came back with sub_type street_robbery
        p = resolve_plan(plan(category="robbery", sub_type="street_robbery"), TODAY, "Robberies with a red Pulsar")
        assert (p.category, p.sub_type) == ("robbery", "") and "does not name street robberies" in p.notes[0]
        p = resolve_plan(plan(sub_type="chain_snatching"), TODAY, "chain snatchings in Adyar")
        assert p.sub_type == "chain_snatching" and p.notes == []

    @pytest.mark.parametrize("question,sub,kept", [
        ("house breaks in Adyar in the last 30 days", "day_house_break", False),  # "days" is not "day"
        ("house breaks in Adyar in the last 30 days", "night_house_break", False),
        ("burglaries tonight in Adyar", "night_house_break", False),  # "tonight" is not "night"
        ("daytime break-in at Adyar", "day_house_break", True),
        ("house breaks during the day this month", "day_house_break", True),
        ("break-ins at night in Velachery", "night_house_break", True),
        ("overnight house breaks last week", "night_house_break", True),
    ])
    def test_day_and_night_cues_are_whole_words(self, question, sub, kept):
        p = resolve_plan(plan(sub_type=sub), TODAY, question)
        assert p.category == "house_break" and (p.sub_type == sub) is kept

    def test_place_aliases_resolve_to_their_station(self):
        assert STATIONS["adayar"][0] == "PS-ADYAR-J2"
        assert resolve_plan(plan(category="robbery", stations=["LB Road"]), TODAY).stations[0][0] == "PS-ADYAR-J2"

    def test_unknown_place_is_unmappable_with_its_name(self):
        with pytest.raises(Unmappable, match="Gotham"):
            resolve_plan(plan(category="robbery", stations=["Gotham"]), TODAY)

    def test_not_a_crime_search_is_unmappable(self):
        with pytest.raises(Unmappable, match="only search crimes"):
            resolve_plan({"answerable": False}, TODAY)

    def test_too_broad_is_unmappable(self):
        with pytest.raises(Unmappable, match="too broad"):
            resolve_plan(plan(time={"kind": "this_month"}), TODAY)

    def test_words_are_single_plain_words_and_category_or_place_words_are_dropped(self):
        p = resolve_plan(plan(category="robbery", words=["Red", "pulsar", "robbery", "adyar", "red"]), TODAY)
        assert p.words == ["red", "pulsar"]
        with pytest.raises(Unmappable):
            resolve_plan(plan(category="robbery", words=["red pulsar"]), TODAY)
        with pytest.raises(Unmappable):
            resolve_plan(plan(category="robbery", words=["' or 1=1 --"]), TODAY)

    def test_hours_are_checked(self):
        assert resolve_plan(plan(category="theft", hours={"from": 19, "to": 24}), TODAY).hours == (19, 24)
        with pytest.raises(Unmappable):
            resolve_plan(plan(category="theft", hours={"from": 25, "to": 3}), TODAY)


class TestTime:
    def test_no_time_means_last_90_days_and_says_so(self):
        since, until, label = resolve_time(None, TODAY)
        assert (until - since).days == DEFAULT_DAYS and "no time given" in label

    def test_relative_windows_resolve_in_code(self):
        assert resolve_time({"kind": "this_month"}, TODAY)[:2] == (date(2026, 10, 1), date(2026, 10, 28))
        assert resolve_time({"kind": "last_month"}, TODAY)[:2] == (date(2026, 9, 1), date(2026, 10, 1))
        assert resolve_time({"kind": "last_days", "days": 90}, TODAY)[:2] == (date(2026, 7, 30), date(2026, 10, 28))
        assert resolve_time({"kind": "since", "date": "2026-09-01"}, TODAY)[0] == date(2026, 9, 1)
        assert resolve_time({"kind": "between", "from": "2026-09-01", "to": "2026-09-30"}, TODAY)[1] == date(2026, 10, 1)

    @pytest.mark.parametrize("t", [{"kind": "next_week"}, {"kind": "since", "date": "2027-01-01"},
                                   {"kind": "last_days", "days": 5000}, {"kind": "between", "from": "2026-10-05",
                                                                          "to": "2026-10-01"}])
    def test_bad_windows_are_unmappable(self, t):
        with pytest.raises(Unmappable):
            resolve_time(t, TODAY)

    def test_hours_wrap_past_midnight(self):
        assert in_hours(23, (22, 6)) and in_hours(2, (22, 6)) and not in_hours(12, (22, 6))
        assert in_hours(19, (19, 24)) and not in_hours(18, (19, 24)) and not in_hours(None, (19, 24))


# =====================
# One question, end to end (fake model + fake Zetaris)
# =====================


def crime(cid, sub="chain_snatching", when="2026-10-20T20:10:00+05:30", text="Two men on a red Pulsar",
          station="PS-ADYAR-J2", cat="robbery"):
    return {"crime_id": cid, "station_id": station, "category": cat, "sub_type": sub, "occurred_from": when,
            "lat": 13.0, "lon": 80.2, "address": "LB Road", "status": "undetected", "severity": 3, "text": text,
            "matched_in": "crime"}


ROWS = [
    crime("CHN-AD-2026-000001"),
    crime("CHN-AD-2026-000002", when="2026-10-21T21:00:00+05:30"),
    crime("CHN-AD-2026-000003", sub="mobile_snatching"),  # wrong sub type
    crime("CHN-AD-2026-000004", text="Two men on a black Splendor"),  # words missing
    crime("CHN-AD-2026-000005", when="2026-10-20T09:00:00+05:30"),  # outside the hours
    crime("CHN-AD-2026-000006", text="[nexus-5 timing test FIR] two men on a red Pulsar"),  # D-033 test FIR
]
PLAN = plan(sub_type="chain_snatching", stations=["Adyar"], time={"kind": "this_month"},
            hours={"from": 19, "to": 24}, words=["red", "pulsar"])


def responder(reply):
    return lambda lane, messages, purpose: reply if isinstance(reply, str) else json.dumps(reply)


class TestAnswerQuestion:
    def test_answers_from_q_search_with_code_filters(self, make_deps):
        deps = make_deps(responder(PLAN), handlers={"q_search": lambda p: ROWS})
        out = answer_question("red pulsar chain snatchings in Adyar after 7 pm this month", deps, today=TODAY)
        assert out.status == "answered"
        assert [r["crime_id"] for r in out.answer["rows"]] == ["CHN-AD-2026-000002", "CHN-AD-2026-000001"]
        assert out.answer["total"] == 2 and out.answer["excluded_test_filings"] == 1
        assert out.answer["summary"].startswith("2 cases match: chain snatchings, at Adyar, FIR mentions red + pulsar")
        assert "(1 test filing excluded.)" in out.answer["summary"]
        assert "chain snatching at Adyar, 21 Oct 2026 21:00" in out.answer["rows"][0]["why"]
        # only the allow-listed query ran, with code-resolved parameters
        (name, agent, params), = deps.zetaris.calls
        assert (name, agent) == ("q_search", "Ask")
        assert params["category"] == "robbery" and params["station_id"] == "PS-ADYAR-J2"
        assert (params["since"], params["until"]) == ("2026-10-01", "2026-10-28")
        assert "red" in params["pattern"] and "pulsar" in params["pattern"]
        assert out.plan["steps"][0]["rows"] == len(ROWS) and out.plan["steps"][0]["query_id"]
        assert {f["label"] for f in out.plan["filters"]} >= {"chain snatching", "test filings excluded"}
        assert (out.model, out.receipt_id) == ("nvidia/test-fast", "rcpt_1")

    def test_one_query_per_station_and_no_duplicate_rows(self, make_deps):
        deps = make_deps(responder(plan(category="robbery", stations=["Adyar", "Velachery"])),
                         handlers={"q_search": lambda p: ROWS[:2]})
        out = answer_question("robberies in Adyar and Velachery", deps, today=TODAY)
        assert [c[2]["station_id"] for c in deps.zetaris.calls] == ["PS-ADYAR-J2", "PS-VELACHERY-J7"]
        assert out.answer["total"] == 2

    def test_unmappable_runs_no_query_and_says_why(self, make_deps):
        deps = make_deps(responder(plan(category="robbery", stations=["Gotham"])), handlers={"q_search": lambda p: ROWS})
        out = answer_question("robberies in Gotham", deps, today=TODAY)
        assert out.status == "unmappable" and "Gotham" in out.answer["summary"]
        assert out.answer["rows"] == [] and deps.zetaris.calls == []

    def test_a_full_page_that_cannot_page_further_is_reported_as_at_least(self, make_deps):
        many = [crime(f"CHN-AD-2026-{i:06d}", text="red pulsar") for i in range(QUERY_LIMIT)]
        deps = make_deps(responder(plan(category="robbery", words=["pulsar"])), handlers={"q_search": lambda p: many})
        out = answer_question("pulsar robberies", deps, today=TODAY)
        assert out.answer["truncated"] and out.answer["summary"].startswith(f"At least {QUERY_LIMIT}")
        assert len(out.answer["rows"]) == 50 and "Showing the newest 50" in out.answer["summary"]

    def test_a_full_page_pages_back_in_time_until_complete(self, make_deps):
        def page(p):
            if p["until"] == "2026-10-28":  # newest page: full, its oldest row on 20 Oct
                return [crime(f"CHN-AD-2026-{i:06d}", text="red pulsar",
                              when="2026-10-20T20:00:00+05:30" if i == 0 else "2026-10-25T20:00:00+05:30")
                        for i in range(QUERY_LIMIT)]
            assert p["until"] == "2026-10-21"  # asked again from the oldest day
            return [crime("CHN-AD-2026-000000", when="2026-10-20T20:00:00+05:30", text="red pulsar"),
                    crime("CHN-AD-2026-999999", when="2026-10-02T20:00:00+05:30", text="red pulsar")]
        deps = make_deps(responder(plan(category="robbery", words=["pulsar"], time={"kind": "this_month"})),
                         handlers={"q_search": page})
        out = answer_question("pulsar robberies this month", deps, today=TODAY)
        assert len(deps.zetaris.calls) == 2 and not out.answer["truncated"]
        assert out.answer["total"] == QUERY_LIMIT + 1 and "page 2" in out.plan["steps"][1]["purpose"]

    def test_no_match_says_so(self, make_deps):
        deps = make_deps(responder(plan(category="homicide")), handlers={"q_search": lambda p: []})
        out = answer_question("murders", deps, today=TODAY)
        assert out.status == "answered" and out.answer["summary"].startswith("No cases match: homicides, last 90 days")

    def test_model_without_json_fails_with_the_reason(self, make_deps):
        deps = make_deps(responder("I think it is the red bike gang."), handlers={"q_search": lambda p: ROWS})
        out = answer_question("who did it?", deps, today=TODAY)
        assert out.status == "failed" and "planning model" in out.error and deps.zetaris.calls == []

    def test_query_failure_fails_the_question(self, make_deps):
        def boom(p):
            raise RuntimeError("Zetaris down")
        deps = make_deps(responder(plan(category="robbery")), handlers={"q_search": boom})
        out = answer_question("robberies", deps, today=TODAY)
        assert out.status == "failed" and "Zetaris down" not in out.error  # officer-safe text; detail in trace
        assert any("Zetaris down" in (e.get("output_summary") or "") for e in deps.tracer.read())

    def test_a_timeout_says_busy_and_queries_fail_fast(self, make_deps):
        from app.adapters.zetaris import ZetarisTimeout

        def slow(p):
            raise ZetarisTimeout("timed out: read timeout")
        deps = make_deps(responder(plan(category="robbery")), handlers={"q_search": slow})
        out = answer_question("robberies", deps, today=TODAY)
        assert out.status == "failed" and "did not answer in time" in out.error

    def test_words_are_whole_words_in_the_narrative_only(self, make_deps):
        rows = [crime("CHN-RH-2026-000001", text="Two men on a black Pulsar"),  # address is "LB Road"; see below
                crime("CHN-RH-2026-000002", text="A reddish Pulsar was seen"),
                crime("CHN-RH-2026-000003", text="two men on red Pulsars")]
        rows[0]["address"] = "Red Hills main road"
        deps = make_deps(responder(plan(category="robbery", words=["red", "pulsar"])), handlers={"q_search": lambda p: rows})
        out = answer_question("red pulsar robberies", deps, today=TODAY)
        assert [r["crime_id"] for r in out.answer["rows"]] == ["CHN-RH-2026-000003"]


def test_understood_reads_plainly():
    p = resolve_plan(plan(status="charge_sheeted", category="house_break", stations=["Adyar"]), TODAY)
    assert understood(p).startswith("house breaks, at Adyar, charge sheet filed")
    assert understood(resolve_plan(plan(category="robbery"), TODAY)).startswith("robberies,")


# =====================
# Worker: claim once, sweep stuck questions
# =====================


class FakeSb:
    def __init__(self, rows):
        self.rows = {r["question_id"]: dict(r) for r in rows}
        self.updates: list[tuple[dict, dict]] = []

    def select(self, table, params):
        return [dict(r) for r in self.rows.values() if r["status"] == "queued"][: int(params.get("limit", 99))]

    def update(self, table, match, values):
        self.updates.append((match, values))
        hit = []
        for r in self.rows.values():
            ok = True
            for k, v in match.items():
                op, _, val = v.partition(".")
                if op == "eq" and str(r.get(k)) != val:
                    ok = False
                if op == "in" and r.get(k) not in val.strip("()").split(","):
                    ok = False
                if op == "lt" and not (r.get(k) and r[k] < val):
                    ok = False
            if ok:
                r.update(values)
                hit.append(r)
        return hit

    def upsert(self, table, rows, on_conflict):
        return []


def test_worker_claims_answers_and_never_answers_twice(tmp_path, make_deps, monkeypatch):
    import app.ask_worker as aw
    from app.config import Settings
    from app.tracing import Tracer

    monkeypatch.setattr(aw, "Tracer", lambda run_id, _dir, echo=False: Tracer(run_id, tmp_path, echo=False))
    sb = FakeSb([{"question_id": "q1", "question": "red pulsar chain snatchings", "status": "queued",
                  "created_at": "2026-10-27T01:00:00+05:30"}])
    deps = make_deps(responder(PLAN), handlers={"q_search": lambda p: ROWS})
    w = AskWorker(Settings(), sb, deps_factory=lambda tracer: deps)
    assert w.run_once() == {"swept": 0, "answered": 1}
    row = sb.rows["q1"]
    assert row["status"] == "answered" and row["run_id"].startswith("ask_") and row["answer"]["total"] == 2
    assert w.claim("q1") is False  # already taken: a second worker copy gets nothing
    assert w.run_once()["answered"] == 0


def test_worker_frees_questions_stuck_past_the_limit():
    from app.config import Settings

    sb = FakeSb([{"question_id": "old", "status": "running", "started_at": "2026-10-27T01:00:00+05:30"},
                 {"question_id": "new", "status": "planning", "started_at": "2026-10-27T01:09:00+05:30"},
                 {"question_id": "done", "status": "answered", "started_at": "2026-10-27T00:00:00+05:30"}])
    w = AskWorker(Settings(), sb)
    from app.ask import TZ
    assert w.sweep_stale(now=datetime(2026, 10, 27, 1, 10, tzinfo=TZ)) == 1
    assert sb.rows["old"]["status"] == "failed" and "Timed out" in sb.rows["old"]["error"]
    assert sb.rows["new"]["status"] == "planning" and sb.rows["done"]["status"] == "answered"
