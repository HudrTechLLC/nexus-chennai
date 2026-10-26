"""Sanitiser (WS2-19), Briefer (WS2-20), Series analyst (LNK-05, LNK-12) and their API routes."""

from __future__ import annotations

import json

import pytest
from agents_fixtures import ADYAR, FEATURES, HOUSEBREAK, VELACHERY, FakeEngines, as_row, default_handlers

from app import engines
from app.agents import Briefer, MemoryStore, Sanitiser, SeriesAnalyst, detect_series
from app.agents.base import crime_from_row, features_from_row
from app.agents.sanitiser import leaks
from app.models import PublicIncident

CASE = crime_from_row(as_row({**ADYAR, "fir_no": "1182/2026",
                              "property": [{"type": "gold_chain", "value_inr": 152000}]}))
FEATS = features_from_row(as_row(FEATURES[ADYAR["crime_id"]]))

# ----- Sanitiser ----------------------------------------------------------------


def test_sanitiser_model_never_sees_private_facts(make_deps):
    seen = []

    def reply(lane, m, p):
        seen.append(m[-1]["content"])
        return json.dumps({"title": "Chain snatching by two riders on a red motorcycle",
                           "summary": "Two men on a red motorcycle snatched a gold chain near a bus stop.",
                           "looking_for": ["Red motorcycle with two riders", "Shop CCTV on LB Road in the evening"]})

    deps = make_deps(responder=reply)
    d = Sanitiser(deps).draft(CASE, FEATS)
    prompt = seen[0]
    for private in ("CHN-AD", "1182/2026", "PS-ADYAR", "TN 09", "4471", "152000", "bus depot", "19:40"):
        assert private not in prompt
    assert d["status"] == "draft" and d["approved_by"] is None and d["source"] == "model"
    assert d["area_label"] == "Adyar (LB Road area)" and d["week"] == "2026-W42" and d["time_window"] == "Evening"
    assert len(d["cell"]) == 15  # H3 r8, never the exact point
    PublicIncident.model_validate({k: v for k, v in d.items() if k not in ("status", "source")}
                                  | {"approved_by": "station_officer:PS-ADYAR-J2"})


def test_sanitiser_rejects_leaky_model_text(make_deps):
    deps = make_deps(responder=lambda *a: json.dumps({
        "title": "Snatching at 7:40 pm", "summary": "Bike TN 09 BX 4471 seen; call 9840012345",
        "looking_for": ["FIR 1182/2026"]}))
    d = Sanitiser(deps).draft(CASE, FEATS)
    assert d["source"] == "template" and d["sanitiser_model"] == "code-template"
    assert not leaks(" ".join([d["title"], d["summary"], *d["looking_for"]]), CASE)


def test_sanitiser_stable_id_reveals_no_case_id(make_deps):
    deps = make_deps(responder=lambda *a: "no json")
    a, b = Sanitiser(deps).draft(CASE, FEATS), Sanitiser(deps).draft(CASE, FEATS)
    assert a["public_incident_id"] == b["public_incident_id"] and "1182" not in a["public_incident_id"]


# ----- Briefer ------------------------------------------------------------------

ALERTS = [
    {"alert_id": "LA-1", "band": "high", "score": 0.82, "stations": ["PS-A", "PS-B"], "status": "pending",
     "rationale": "Same red Pulsar"},
    {"alert_id": "LA-2", "band": "medium", "score": 0.6, "stations": ["PS-A"], "status": "pending"},
]
DECISIONS = [{"decision": "reject", "reason_code": "different_offenders"}, {"decision": "approve"}]


def test_briefer_uses_model_prose_when_numbers_check_out(make_deps):
    deps = make_deps(responder=lambda *a: json.dumps({"briefing": "2 new alerts, 1 high. Start with LA-1."}))
    out = Briefer(deps).brief("South", "2026-10-26", ALERTS, DECISIONS)
    assert out["source"] == "model" and out["lane"] == "fast"  # no tiny lane configured -> E2 fallback
    assert out["facts"]["cross_station"] == 1 and out["facts"]["rejected"] == 1


def test_briefer_rejects_invented_numbers(make_deps):
    deps = make_deps(responder=lambda *a: json.dumps({"briefing": "17 new alerts overnight."}))
    out = Briefer(deps).brief("South", "2026-10-26", ALERTS, DECISIONS)
    assert out["source"] == "template" and "2 new link alerts" in out["text"]


# ----- Series ---------------------------------------------------------------------


def test_detect_series_needs_three_connected_cases_and_ignores_rejected():
    alerts = [{"alert_id": "1", "crimes": ["a", "b"], "stations": ["S1"], "score": 0.8},
              {"alert_id": "2", "crimes": ["b", "c"], "stations": ["S2"], "score": 0.7},
              {"alert_id": "3", "crimes": ["x", "y"], "score": 0.9},
              {"alert_id": "4", "crimes": ["y", "z"], "score": 0.9, "status": "rejected"}]
    s = detect_series(alerts)
    assert len(s) == 1 and s[0]["crime_ids"] == ["a", "b", "c"] and s[0]["stations"] == ["S1", "S2"]
    assert s[0]["series_id"] == detect_series(list(reversed(alerts)))[0]["series_id"]


def test_series_dossier_cites_only_real_records(make_deps):
    handlers = default_handlers()
    case_with_statement = {**ADYAR, "statements": [{"statement_id": "ST-1", "text": "Two boys on a red bike"}]}
    crimes = {c["crime_id"]: c for c in (case_with_statement, VELACHERY, HOUSEBREAK)}
    handlers["q_case"] = lambda p: [as_row(crimes[p["crime_id"]])]
    handlers["q_tip_corroboration"] = lambda p: [{"tip_id": "TIP-1", "text": "Red bike parks near tea shop",
                                                  "received_week": "2026-W43"}]

    def reply(lane, m, p):
        return "Notes: same red bike [CHN-AD-2026-001182] [TIP-1] and an invented [FAKE-9].\n[TASK_COMPLETE]\n" \
               "[STATE_CHECKPOINT]\nCOMPLETED: read 5 of 5 records\nREMAINING: 0\nDECISIONS: recurring MO red bike\n" \
               "CONTEXT: open leads TIP-1"

    deps = make_deps(responder=reply, handlers=handlers, engines=engines)
    out = SeriesAnalyst(deps).dossier("SER-T", [ADYAR["crime_id"], VELACHERY["crime_id"], HOUSEBREAK["crime_id"]])
    assert "FAKE-9" not in out["cited_ids"] and "FAKE-9" in out["dropped_citations"]
    assert "TIP-1" in out["cited_ids"] and out["record_count"] == 5
    assert out["chunks"] >= 1 and {"tokens_projected", "tokens_actual"} <= set(out)
    assert deps.nightshift.calls[0][0] == "reason"
    assert out["model"] == "nvidia/test-reason" and out["receipt_id"] == out["receipt_ids"][-1]


def test_series_dossier_falls_back_per_chunk(make_deps):
    deps = make_deps(responder=lambda *a: "no checkpoint here", engines=engines)
    out = SeriesAnalyst(deps).dossier("SER-T", [ADYAR["crime_id"], VELACHERY["crime_id"]])
    assert out["cited_ids"] and any(e["action"] == "chunk_fallback" for e in deps.tracer.read())
    assert out["model"] is None and out["receipt_ids"] == []  # no model wrote any of it


# ----- API routes -------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, make_deps):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from app import main

    @contextmanager
    def fake_deps(settings, run_id, **kw):
        yield make_deps(responder=lambda *a: "{}", engines=engines)

    monkeypatch.setattr(main, "agent_deps", fake_deps)
    store = MemoryStore()
    monkeypatch.setattr(main, "default_store", lambda settings, tracer: store)
    c = TestClient(main.app)
    c.store = store  # type: ignore[attr-defined]
    return c


def test_public_draft_route(client):
    r = client.post(f"/api/cases/{ADYAR['crime_id']}/public-draft")
    assert r.status_code == 200 and r.json()["status"] == "draft"
    assert client.post("/api/cases/NOPE/public-draft").status_code == 404


def test_dossier_and_briefing_routes(client):
    r = client.post("/api/series/SER-1/dossier", json={"crime_ids": [ADYAR["crime_id"], VELACHERY["crime_id"]]})
    assert r.status_code == 200 and r.json()["series_id"] == "SER-1"
    saved = client.store.series["SER-1"]["dossier"]
    assert set(saved) >= {"text", "cited_ids", "chunks", "tokens_projected", "tokens_actual", "model", "receipt_id",
                          "run_id", "generated_at"} and saved["run_id"] == r.json()["run_id"]
    assert r.json()["persisted"] is False  # memory store: nothing reached Supabase
    r = client.post("/api/briefing", json={"zone": "South", "day": "2026-10-26", "alerts": ALERTS})
    assert r.status_code == 200 and r.json()["facts"]["new_alerts"] == 2


def test_traces_route_rejects_path_tricks(client):
    assert client.get("/api/traces/..%2f..%2fetc").status_code in (400, 404)
    assert client.get("/api/traces/run_doesnotexist").status_code == 404


_ = FakeEngines


def test_series_dossier_without_tip_query_and_with_summary_tips(make_deps):
    """q_tip_corroboration is not registered live yet: the dossier must still be written. When it exists,
    rows come from tips_v (vocabulary summary, no raw text) and the summary is what the dossier reads."""
    handlers = default_handlers()
    del handlers["q_tip_corroboration"]
    deps = make_deps(responder=lambda *a: "no checkpoint", handlers=handlers, engines=engines)
    out = SeriesAnalyst(deps).dossier("SER-T", [ADYAR["crime_id"], VELACHERY["crime_id"]])
    assert out["cited_ids"] and any(e["action"] == "tips_unavailable" for e in deps.tracer.read())

    handlers = default_handlers()
    handlers["q_tip_corroboration"] = lambda p: [{"tip_id": "TIP-9", "summary": "Tip mentions: red, motorcycle.",
                                                  "received_week": "2026-W43"}]
    deps = make_deps(responder=lambda *a: "no checkpoint", handlers=handlers, engines=engines)
    recs = SeriesAnalyst(deps).records([ADYAR["crime_id"]])
    assert {"id": "TIP-9", "kind": "tip", "date": "2026-W43", "text": "Tip mentions: red, motorcycle."} in recs
