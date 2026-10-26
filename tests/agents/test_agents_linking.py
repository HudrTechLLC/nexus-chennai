"""Planner, Linker (WS2-11), Skeptic and Alert writer (WS2-13)."""

from __future__ import annotations

import json

import pytest
from agents_fixtures import ADYAR, CRIMES, FEATURES, HOUSEBREAK, VELACHERY, FakeEngines, FakeHmem, as_row, \
    default_handlers

from app.agents import AlertWriter, Candidate, Linker, Planner, Skeptic
from app.agents.base import crime_from_row, features_from_row
from app.agents.planner import default_plan, validate_steps
from app.models import LinkAlert

CASE = crime_from_row(as_row(ADYAR))
CASE_F = FEATURES[ADYAR["crime_id"]]


def candidates():
    return [Candidate(crime_from_row(as_row(c)), features_from_row(as_row(FEATURES[c["crime_id"]])),
                      query_ids={"q_case": "qc", "q_features": "qf"})
            for c in (VELACHERY, HOUSEBREAK)]


# ----- Planner -----------------------------------------------------------------

def test_validate_steps_allowlist_clamp_and_case_id():
    steps, notes = validate_steps([
        {"name": "q_news", "params": {"crime_id": "OTHER"}},
        {"name": "DROP TABLE", "params": {}},
        {"name": "q_candidates", "params": {"crime_id": "X", "days": 400, "ring": 40}},
        {"name": "q_vehicle_trail", "params": {"plate_pattern": "TN09"}},  # missing params
    ], CASE)
    assert [s.name for s in steps] == ["q_candidates", "q_news"]
    assert steps[0].params == {"crime_id": ADYAR["crime_id"], "days": 90, "ring": 10}  # ring = km, max 10
    assert steps[1].params["crime_id"] == ADYAR["crime_id"]  # never model-supplied
    assert any("unknown" in n for n in notes) and any("clamped" in n for n in notes)


def test_planner_uses_model_plan(make_deps):
    plan = {"steps": [{"name": "q_candidates", "params": {"days": 20, "ring": 1}, "why": "block"},
                      {"name": "q_vehicle_trail", "params": {"plate_pattern": "TN09??4471", "t0": "a", "t1": "b",
                                                             "cells": ["x", "y"]}}]}
    deps = make_deps(responder=lambda lane, m, p: json.dumps(plan))
    p = Planner(deps).plan(CASE, CASE_F)
    # recall floor: the model asked 20 days / 1 km; blocking keeps at least 45 days / 6 km (hero pair is 3.5 km)
    assert p.source == "model" and p.steps[0].params["days"] == 45 and p.steps[0].params["ring"] == 6
    assert any("recall floor" in n for n in p.notes)
    adj = [e for e in deps.tracer.read() if e["action"] == "plan_adjusted"]
    assert adj and json.loads(adj[0]["output_summary"]) == {"model": {"days": 20, "ring": 1},
                                                            "applied": {"days": 45, "ring": 6}, "reason": "recall_floor"}
    assert p.steps[1].params["cells"] == "x,y"


def test_planner_may_widen_the_window(make_deps):
    plan = {"steps": [{"name": "q_candidates", "params": {"days": 80, "ring": 9}}]}
    deps = make_deps(responder=lambda lane, m, p: json.dumps(plan))
    p = Planner(deps).plan(CASE, CASE_F)
    assert p.steps[0].params["days"] == 80 and p.steps[0].params["ring"] == 9
    assert deps.nightshift.calls[0][0] == "reason"


def test_planner_falls_back_to_default_plan(make_deps):
    deps = make_deps(responder=lambda lane, m, p: '{"steps": [{"name": "q_news"}]}')
    p = Planner(deps).plan(CASE, CASE_F)
    assert p.source == "default" and p.steps[0].name == "q_candidates"
    assert "q_vehicle_trail" in [s.name for s in p.steps]


def test_planner_execute_runs_named_queries(make_deps):
    deps = make_deps()
    out = Planner(deps).execute(Planner(deps).plan(CASE, CASE_F))
    assert len(out["q_candidates"]["rows"]) == 2
    assert all(agent == "Planner" for _, agent, _ in deps.zetaris.calls)


def test_planner_drops_steps_with_empty_parameters():
    """Live Ultra output had q_offender_return with mo_tags '' - that would search the whole ward."""
    steps, notes = validate_steps([
        {"name": "q_candidates", "params": {"days": 30, "ring": 1}},
        {"name": "q_offender_return", "params": {"mo_tags": "", "ward": 173, "since": "2026-07-15T00:00:00+05:30"}},
        {"name": "q_vehicle_trail", "params": {"plate_pattern": "TN09", "t0": "a", "t1": "b", "cells": []}},
    ], CASE)
    assert [s.name for s in steps] == ["q_candidates"]


def test_agents_fall_back_when_nightshift_fails(make_deps):
    from app.adapters.nightshift import NightshiftError

    def down(lane, m, p):
        raise NightshiftError("unreachable and no recorded fixture")
    deps = make_deps(responder=down)
    plan = Planner(deps).plan(CASE, CASE_F)
    assert plan.source == "default"
    linker = Linker(deps)
    pairs = linker.score(CASE, CASE_F, candidates(), support(deps))
    linker.explain(pairs)
    assert all("computed in code" in f.reason for f in pairs[0].score.factors if f.value is not None)
    res = Skeptic(deps).review([p for p in pairs if p.score.alert])
    assert res[0].verdict == "approve"  # code verdict stands without the critique


def test_model_prompts_are_replayable(make_deps):
    """R6: prompts must not contain per-call query ids, or sample-mode fixtures never match."""
    from app.adapters.nightshift import fixture_key
    keys = []
    for _ in range(2):
        prompts = []
        deps = make_deps(responder=lambda lane, m, p: prompts.append(m) or "{}")
        linker = Linker(deps)
        linker.explain(linker.score(CASE, CASE_F, candidates(), support(deps)))
        keys.append(fixture_key("reason", prompts[-1]))
    assert keys[0] == keys[1]


def test_default_plan_never_includes_tip_text():
    for s in default_plan(CASE, CASE_F):
        assert "text" not in s.params


# ----- Linker ------------------------------------------------------------------

def support(deps):
    planner = Planner(deps)
    return planner.execute(planner.plan(CASE, CASE_F))


def test_linker_scores_planted_pair_high_and_decoy_low(make_deps):
    deps = make_deps(responder=lambda lane, m, p: "{}")
    pairs = Linker(deps).score(CASE, CASE_F, candidates(), support(deps))
    by = {p.crime_b["crime_id"]: p for p in pairs}
    assert by[VELACHERY["crime_id"]].score.alert and by[VELACHERY["crime_id"]].score.band == "high"
    assert not by[HOUSEBREAK["crime_id"]].score.alert
    veh = next(f for f in by[VELACHERY["crime_id"]].score.factors if f.factor == "vehicle")
    assert veh.value == pytest.approx(0.85)  # ANPR read near both scenes
    assert any(e.get("query") == "q_vehicle_trail" and e.get("query_id") for e in veh.evidence)


def test_linker_applies_memory_with_engine_pair_shape(make_deps):
    hm = FakeHmem(delta=-0.05)
    deps = make_deps(engines=FakeEngines(hmem=hm))
    pairs = Linker(deps).score(CASE, CASE_F, candidates(), support(deps))
    v = next(p for p in pairs if p.crime_b["crime_id"] == VELACHERY["crime_id"])
    assert v.score.memory_delta == pytest.approx(-0.05) and v.score.memory_applied[0]["memory_id"] == "HM-1"
    assert "crime_id" not in json.dumps(hm.pairs[0])  # MO-only memory key


def test_linker_with_real_hmem_engine(make_deps):
    from app import engines
    deps = make_deps(engines=engines)
    pairs = Linker(deps).score(CASE, CASE_F, candidates(), support(deps))
    assert all(abs(p.score.memory_delta) <= 0.08 for p in pairs)


def test_explain_sets_reasons_but_never_numbers(make_deps):
    def responder(lane, m, p):
        payload = json.loads(m[-1]["content"]) if m[-1]["content"].startswith("{") else {}
        pid = next(iter(payload), "x")
        return json.dumps({"pairs": {pid: {"factors": {"vehicle": "Same plate on ANPR", "mo_similarity": 0.01},
                                           "rationale": "Same pattern", "recommended_action": "Joint review",
                                           "score": 0.01}}})
    deps = make_deps(responder=responder)
    linker = Linker(deps)
    pairs = linker.score(CASE, CASE_F, candidates(), support(deps))
    before = pairs[0].score.score
    linker.explain(pairs)
    p = pairs[0]
    assert p.score.score == before
    reasons = {f.factor: f.reason for f in p.score.factors if f.value is not None}
    assert reasons["vehicle"] == "Same plate on ANPR"
    assert "computed in code" in reasons["mo_similarity"]  # non-text model output ignored
    assert p.rationale == "Same pattern"


# ----- Skeptic ------------------------------------------------------------------

def scored(deps):
    linker = Linker(deps)
    pairs = linker.score(CASE, CASE_F, candidates(), support(deps))
    return [p for p in pairs if p.score.alert]


def approve_all(lane, m, p):
    if "critique" not in p:
        return "{}"
    payload = json.loads(m[-1]["content"])
    return json.dumps({"pairs": {k: {"verdict": "approve", "critique": "ok"} for k in payload}})


def test_skeptic_approves_supported_pair(make_deps):
    deps = make_deps(responder=approve_all)
    res = Skeptic(deps).review(scored(deps))
    assert res[0].verdict == "approve" and res[0].struck == []
    assert any(c[0] == "q_case" and c[1] == "Skeptic" for c in deps.zetaris.calls)  # own re-query


def test_skeptic_strikes_factor_its_rows_do_not_support(make_deps):
    handlers = default_handlers()
    deps = make_deps(responder=approve_all, handlers=handlers)
    pairs = scored(deps)
    # Fresh rows: no ANPR reads, and the Velachery FIR now records a different plate.
    handlers["q_vehicle_trail"] = lambda p: []
    changed = {**VELACHERY, "vehicles": [{**VELACHERY["vehicles"][0], "plate": "TN10ZZ0000"}]}
    handlers["q_case"] = lambda p: [as_row(changed if p["crime_id"] == VELACHERY["crime_id"]
                                           else CRIMES[p["crime_id"]])]
    before = pairs[0].score.score
    res = Skeptic(deps).review(pairs)[0]
    assert "vehicle" in res.struck and res.pair.score.score < before
    strikes = [e for e in deps.tracer.read() if e["action"] == "strike_factor"]
    assert strikes and strikes[0]["target_agent"] == "Linker" and strikes[0]["status"] == "needs_revision"


def test_skeptic_keeps_factor_when_its_requery_is_unavailable(make_deps):
    """Live regression (run_85d1be81): q_vehicle_trail not registered crashed the run in the Skeptic.
    A failed support re-query leaves the factor unverified (kept, traced), never struck."""
    handlers = default_handlers()
    deps = make_deps(responder=approve_all, handlers=handlers)
    pairs = scored(deps)
    del handlers["q_vehicle_trail"]  # FakeZetaris raises KeyError, like UnknownQuery on the live registry
    before = pairs[0].score.score
    res = Skeptic(deps).review(pairs)[0]
    assert "vehicle" not in res.struck and res.pair.score.score == before
    assert any(e["action"] == "recheck_unavailable" and "q_vehicle_trail" in e["input_summary"]
               for e in deps.tracer.read())


def test_skeptic_drops_when_strikes_kill_the_alert(make_deps):
    handlers = default_handlers()
    deps = make_deps(responder=approve_all, handlers=handlers)
    pairs = scored(deps)
    handlers["q_case"] = lambda p: []  # nothing re-checks
    res = Skeptic(deps).review(pairs)[0]
    assert res.verdict == "drop" and not res.pair.score.alert


def test_skeptic_model_can_only_downgrade_and_send_back_is_capped(make_deps):
    def send_back(lane, m, p):
        if "critique" not in p:
            return "{}"
        payload = json.loads(m[-1]["content"])
        return json.dumps({"pairs": {k: {"verdict": "send_back", "critique": "window too wide",
                                         "requery": {"days": 10, "ring": 0}} for k in payload}})
    deps = make_deps(responder=send_back)
    pairs = scored(deps)
    r1 = Skeptic(deps).review(pairs, round_no=1)[0]
    assert r1.verdict == "send_back" and r1.requery["days"] == 10
    r3 = Skeptic(deps).review(pairs, round_no=3)[0]
    assert r3.verdict == "approve" and "cap" in r3.critique


def test_forensic_exemption_requires_skeptic_recheck(make_deps):
    """D-016: an unstruck forensic match is exempt from the coverage guard, but only after the
    Skeptic re-queries the forensic rows itself; if they don't match, the factor is struck and
    the normal coverage rules apply."""
    a = {**HOUSEBREAK, "crime_id": "F-A", "forensics": [{"forensic_id": "FO-1", "match_code": "FP-77"}]}
    b = {**HOUSEBREAK, "crime_id": "F-B", "lat": 13.2, "occurred_from": "2026-06-01T02:00:00+05:30",
         "category": "robbery", "forensics": [{"forensic_id": "FO-2", "match_code": "FP-77"}]}
    crimes = {a["crime_id"]: a, b["crime_id"]: b}
    handlers = default_handlers()
    handlers["q_case"] = lambda p: [as_row(crimes[p["crime_id"]])] if p["crime_id"] in crimes else []
    handlers["q_features"] = lambda p: []
    deps = make_deps(responder=approve_all, handlers=handlers)
    pa = crime_from_row(as_row(a))
    pairs = Linker(deps).score(pa, None, [Candidate(crime_from_row(as_row(b)), None)], {})
    sp = pairs[0]
    assert sp.score.alert and sp.score.band == "high" and sp.score.coverage < 0.5  # exempt from the cap

    # Skeptic confirms the match from its own rows -> the exempt alert stands.
    ok = Skeptic(deps).review([sp])[0]
    assert ok.verdict == "approve" and "forensic" not in ok.struck

    # The fresh forensic rows no longer match -> struck, coverage guard applies -> dropped.
    pairs = Linker(deps).score(pa, None, [Candidate(crime_from_row(as_row(b)), None)], {})
    crimes[b["crime_id"]] = {**b, "forensics": [{"forensic_id": "FO-2", "match_code": "FP-99"}]}
    bad = Skeptic(deps).review(pairs)[0]
    assert "forensic" in bad.struck and not bad.pair.score.forensic_floor_applied
    assert bad.pair.score.band != "high"  # coverage 0.35 < 0.50: the guard applies again


# ----- Alert writer ---------------------------------------------------------------

def test_alert_writer_writes_valid_d3_11_alert(make_deps):
    deps = make_deps(responder=approve_all)
    pairs = scored(deps)
    Linker(deps).explain(pairs)
    results = Skeptic(deps).review(pairs)
    written = AlertWriter(deps).write(results)
    assert len(written) == 1
    row = written[0]
    LinkAlert.model_validate({k: v for k, v in row.items() if k != "synthetic"})
    assert row["status"] == "pending" and row["kind"] == "pair"
    assert set(row["stations"]) == {ADYAR["station_id"], VELACHERY["station_id"]}
    assert row["skeptic"] == {"rounds": 1, "struck": [], "verdict": "approved", "model_critique": "applied"}
    assert all(f["value"] is not None and f["reason"] for f in row["factors"])
    assert any(e.get("query_id") for f in row["factors"] for e in f["evidence"])
    assert row["coverage"] > 0.5 and row["synthetic"] is True
    assert {n["station_id"] for n in deps.store.notifications} == set(row["stations"])


def test_alert_id_is_stable_per_pair():
    from app.agents.alert_writer import alert_id_for
    assert alert_id_for(["B", "A"], 2026) == alert_id_for(["A", "B"], 2026)
    assert alert_id_for(["A", "B"], 2026) != alert_id_for(["A", "C"], 2026)


def test_alert_writer_skips_dropped(make_deps):
    handlers = default_handlers()
    deps = make_deps(responder=approve_all, handlers=handlers)
    pairs = scored(deps)
    handlers["q_case"] = lambda p: []
    assert AlertWriter(deps).write(Skeptic(deps).review(pairs)) == []


def test_agents_read_only_through_named_queries():
    """R1: agent code never imports a database or HTTP client directly."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "services" / "api" / "app" / "agents"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for n in names:
                    assert not any(x in n for x in ("duckdb", "psycopg", "httpx", "supabase", "openai")), \
                        f"{path.name} imports {n}"


_ = CRIMES  # data shared with fixtures


def test_mo_cosine_flag_default_off(monkeypatch):
    """D-027 trial: engines.similarity.mo_cosine replaces the text cosine only when NEXUS_MO_COSINE is on."""
    from app.agents.linker import mo_text_cosine
    from app.engines.similarity import mo_cosine
    from app.scoring import factors as F
    monkeypatch.delenv("NEXUS_MO_COSINE", raising=False)
    assert mo_text_cosine() is None
    monkeypatch.setenv("NEXUS_MO_COSINE", "1")
    assert mo_text_cosine() is mo_cosine
    fa, fb = FEATURES[ADYAR["crime_id"]], FEATURES[VELACHERY["crime_id"]]
    from app.agents.base import features_from_row
    a, b = features_from_row(as_row(fa)), features_from_row(as_row(fb))
    assert F.mo_similarity(a, b, text_cosine=mo_cosine) != F.mo_similarity(a, b)


def test_default_plan_finds_hero_pair_in_sample_bundle(tmp_path):
    """Regression (nexus-7 judge's-eye run): ring is a radius in KM for q_candidates; the default plan used 1,
    so VL-000877 (3.46 km from AD-001182) was never a candidate and the hero pair could not alert."""
    from app.adapters.zetaris import ZetarisClient
    from app.config import Settings
    from app.tracing import Tracer
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    z = ZetarisClient(s, Tracer("t", tmp_path, echo=False))
    try:
        case = crime_from_row(z.named("q_case", agent="t", crime_id="CHN-AD-2026-001182").dicts()[0])
        step = default_plan(case, None)[0]
        assert step.name == "q_candidates" and step.params["ring"] == 6
        ids = {r["crime_id"] for r in z.named("q_candidates", agent="t", **step.params).dicts()}
    finally:
        z.close()
    assert "CHN-VL-2026-000877" in ids


def test_rationale_prompt_never_carries_protected_attributes():
    """LNK-13: an FIR's offenders_described may carry gender/complexion; only allow-listed keys reach the model."""
    from app.agents.linker import described
    c = {"offenders_described": [{"age_band": "20-30", "gender": "male", "complexion": "dark", "build": "thin",
                                  "helmet": "black"}]}
    assert described(c) == [{"age_band": "20-30", "build": "thin", "helmet": "black"}]


def test_skeptic_marks_critique_applied(make_deps):
    deps = make_deps(responder=approve_all)
    res = Skeptic(deps).review(scored(deps))[0]
    assert res.model_critique == "applied" and res.review_block()["model_critique"] == "applied"


def test_skeptic_failed_critique_is_marked_on_the_alert(make_deps):
    """Live: a cut-off 7-pair critique returned no `pairs`; the code verdicts stood with no sign of it.
    Now the alert's skeptic block says the model critique was unavailable, and the trace says why."""
    def cut_off(lane, m, p):
        return "{}" if "critique" not in p else '{"verdict": "drop", "critique": "draft"} and then'

    deps = make_deps(responder=cut_off)
    res = Skeptic(deps).review(scored(deps))[0]
    assert res.verdict == "approve" and res.model_critique == "unavailable"
    failed = [e for e in deps.tracer.read() if e["action"] == "critique_failed"]
    assert failed and failed[0]["status"] == "degraded"
    alert = AlertWriter(deps).write([res])[0]
    assert alert["skeptic"]["model_critique"] == "unavailable"


def test_skeptic_pair_missing_from_critique_is_unavailable(make_deps):
    def other_pair(lane, m, p):
        return "{}" if "critique" not in p else json.dumps({"pairs": {"someone-else": {"verdict": "drop"}}})

    deps = make_deps(responder=other_pair)
    res = Skeptic(deps).review(scored(deps))[0]
    assert res.verdict == "approve" and res.model_critique == "unavailable"
    assert any(e["action"] == "critique_missing" for e in deps.tracer.read())


def test_trace_keeps_whole_skeptic_critique_and_linker_rationale(make_deps):
    """nexus-7 on run_da0092da: the stored trace cut the drop reason mid-sentence (160 chars)."""
    critique = "Same night and same MO, but " + "the second FIR's plate read is partial and unverified; " * 6
    rationale = "Both FIRs describe " + "two riders on a red Pulsar snatching chains near bus stops; " * 8

    def long_texts(lane, m, p):
        if "critique" in p:
            payload = json.loads(m[-1]["content"])
            return json.dumps({"pairs": {k: {"verdict": "approve", "critique": critique} for k in payload}})
        if "rationale" in p:
            payload = json.loads(m[-1]["content"])
            return json.dumps({"pairs": {k: {"rationale": rationale} for k in payload}})
        return "{}"

    deps = make_deps(responder=long_texts)
    pairs = scored(deps)
    Linker(deps).explain(pairs)
    Skeptic(deps).review(pairs)
    ev = deps.tracer.read()
    explained = [e for e in ev if e["action"] == "explain_pair"]
    approved = [e for e in ev if e["agent_name"] == "Skeptic" and e["action"] == "approve"]
    assert explained and explained[0]["output_summary"] == rationale.strip()[:600]
    assert approved and approved[0]["output_summary"].endswith(critique[:400])
