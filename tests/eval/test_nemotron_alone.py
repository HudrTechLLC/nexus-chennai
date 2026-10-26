"""Nemotron-alone baseline (engg/docs/eval/NEMOTRON_ALONE_PREREG.md): the committed case/pair list and prompt,
the blinding of the prompt payload, and the scoring. No model calls."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.eval import nemotron_alone as n
from app.eval.core import load_truth


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(n.CASES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def truth():
    return load_truth(n.TRUTH_DIR)


def test_committed_list_is_tied_to_the_headline_truth(plan, truth):
    assert plan["truth_sha256"] == n.truth_hashes()
    assert plan["headline"]["reproduced"] is True
    head = json.loads(n.HEADLINE_REPORT.read_text(encoding="utf-8"))
    assert plan["headline"]["git_commit"] == head["provenance"]["git_commit"]
    assert {k: plan["headline"][k] for k in ("tp", "fp", "fn")} == {k: head["agent"][k] for k in ("tp", "fp", "fn")}


def test_cases_follow_the_stated_rule(plan, truth):
    assert plan["cases"] == truth.crimes()[::n.CASE_EVERY]
    assert len(plan["cases"]) == 20
    per_case: dict[str, int] = {}
    keys = set()
    for p in plan["pairs"]:
        a, b = p["pair"].split("|")
        assert a < b and p["case"] in (a, b)
        assert (a, b) not in keys
        keys.add((a, b))
        per_case[p["case"]] = per_case.get(p["case"], 0) + 1
        assert 1 <= p["rank"] <= n.PAIRS_PER_CASE
    assert max(per_case.values()) <= n.PAIRS_PER_CASE


def test_prompt_is_fixed(plan):
    prompt = n.load_prompt()
    assert prompt["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert prompt["temperature"] == 0
    assert prompt["lane"] == "reason"
    assert "{evidence}" in prompt["user_template"]


def _crime(cid: str, **kw) -> dict:
    base = {"crime_id": cid, "fir_no": "1/2026", "station_id": "PS-X", "source_row_id": "u", "h3_r9": "89",
            "category": "robbery", "occurred_from": "2026-09-01T10:00:00+05:30", "lat": 13.0, "lon": 80.2,
            "narrative": "chain snatched", "statements": [{"statement_id": "ST-1", "text": "red bike"}]}
    return {**base, **kw}


def test_evidence_carries_no_identifiers_and_no_scores():
    a = _crime("CHN-AA-2026-000001")
    b = _crime("CHN-BB-2026-000002", occurred_from="2026-09-02T10:00:00+05:30", lat=13.01)
    feats = {"crime_id": "CHN-AA-2026-000001", "receipt_id": "chatcmpl-x", "mo": {"approach": "x"},
             "visual_tags": [], "entities": {}}
    ev = n.pair_evidence((a, feats), (b, None))
    text = json.dumps(ev)
    for leak in ("CHN-AA", "CHN-BB", "fir_no", "station_id", "source_row_id", "h3_r9", "receipt_id", "ST-1"):
        assert leak not in text
    assert ev["hours_between_start_times"] == 24.0
    assert 1.0 < ev["distance_km"] < 1.2
    assert ev["crime_A"]["witness_statements"] == ["red bike"]
    assert ev["crime_B"]["extracted_features"] is None


def test_blind_assert_catches_truth_leaks():
    terms = n.blind_terms()
    assert "SER-RED-PULSAR" in terms
    n.assert_blind("two robberies on a red motorcycle", terms)
    for bad in ("series_id: x", "SER-RED-PULSAR", "Red Pulsar Duo", "CHN-AD-2026-001071", "the _truth dir",
                "group DEC-01"):
        with pytest.raises(AssertionError):
            n.assert_blind(bad, terms)
    with pytest.raises(AssertionError):
        n.assert_blind("crime X-1 vs X-2", set(), ("X-1", "X-2"))


def test_committed_pairs_render_blind(plan, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    from app.config import get_settings
    from app.eval.core import Evaluator

    get_settings.cache_clear()
    try:
        _, _, z, deps = n._sample_deps("test_nemotron_alone")
        ev = Evaluator(deps, load_truth(n.TRUTH_DIR))
        prompt, terms = n.load_prompt(), n.blind_terms()
        for p in plan["pairs"][:6]:
            a, b = p["pair"].split("|")
            msgs = n.build_messages(prompt, n.pair_evidence(ev._case(a), ev._case(b)))
            n.assert_blind(msgs[1]["content"], terms, (a, b))
            assert msgs[0]["content"] == prompt["system"]
        z.close()
    finally:
        get_settings.cache_clear()


def test_parse_verdict_takes_the_boolean_and_never_thresholds():
    assert n.parse_verdict({"link": True, "confidence": 0.1}) == (True, 0.1)
    assert n.parse_verdict({"link": False, "confidence": "0.9"}) == (False, 0.9)
    assert n.parse_verdict({"link": True}) == (True, None)
    with pytest.raises(ValueError):
        n.parse_verdict({"link": "yes"})


def test_score_uses_only_the_pair_set_and_drops_duplicates():
    pairs = [("a", "b"), ("a", "c"), ("a", "d"), ("a", "e")]
    positives = {("a", "b"), ("a", "c"), ("x", "y")}  # ("x","y") is outside the set: not counted
    dups = {("a", "e")}
    m = n.score(pairs, {("a", "b"), ("a", "d"), ("a", "e")}, positives, dups)
    assert (m["tp"], m["fp"], m["fn"]) == (1, 1, 1)


def test_no_supabase_on_this_path():
    src = Path(n.__file__).read_text(encoding="utf-8")
    assert "SupabaseClient" not in src and "adapters.supabase" not in src and "import supabase" not in src


# =====================
# run(): mocked Nightshift (no model calls)
# =====================

def _mini_plan(plan: dict, tmp_path: Path, n_cases: int = 2, per_case: int = 2) -> Path:
    cases = plan["cases"][:n_cases]
    pairs = []
    for c in cases:
        pairs += [p for p in plan["pairs"] if p["case"] == c][:per_case]
    mini = {**plan, "cases": cases, "pairs": pairs}
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(mini), encoding="utf-8")
    return path


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"model": "nvidia/nemotron-3-ultra-550b-a55b",
                                     "choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


@pytest.fixture
def live_env(monkeypatch, plan, tmp_path):
    from app.config import get_settings

    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("ZETARIS_API_KEY", raising=False)
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "test-token-not-a-secret")
    monkeypatch.setattr(n, "CASES_PATH", _mini_plan(plan, tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_run_scores_both_systems_on_the_same_pairs(live_env, plan):
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        sent.append(body)
        assert body["model"] == "nvidia/nemotron-3-ultra-550b-a55b" and body["temperature"] == 0
        n.assert_blind(body["messages"][1]["content"], n.blind_terms())
        return _reply('{"link": true, "confidence": 0.7, "reason": "same bike"}')

    out = live_env / "out.json"
    doc = n.run(out, transport=httpx.MockTransport(handler))
    mini = json.loads(n.CASES_PATH.read_text(encoding="utf-8"))
    assert len(sent) == len(mini["pairs"]) == doc["pairs_scored"]
    assert doc["cases_completed"] == 2 and doc["failed_calls"] == 0 and doc["stopped_early"] is None
    assert doc["supabase_writes"] == 0 and doc["model"] == "nvidia/nemotron-3-ultra-550b-a55b"
    m = doc["metrics_on_pair_set"]
    assert m["nemotron_alone"]["fn"] == 0  # linked everything
    rec = doc["recall_vs_all_positives_of_completed_cases"]
    assert rec["full_system"] >= m["full_system"]["tp"]  # the system's whole alert set, not only the 10 nearest
    assert all(r["status"] == "ok" and r["model_link"] is True for r in doc["pairs"])
    assert out.read_bytes().count(b"\r\n") == 0

    # resume: completed cases are reused verbatim, no new calls
    sent.clear()
    again = n.run(out, transport=httpx.MockTransport(handler))
    assert sent == [] and again["pairs"] == doc["pairs"]


def test_run_stops_after_three_failed_calls(live_env):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": "bad request"})

    doc = n.run(live_env / "out.json", transport=httpx.MockTransport(handler))
    # case 1 completes with 2 failed calls (scored as no-link); the 3rd failure, in case 2, stops the run and
    # the unfinished case 2 is not scored
    assert doc["stopped_early"] == "3 consecutive failed calls"
    assert doc["cases_completed"] == 1 and doc["pairs_scored"] == 2 and doc["failed_calls"] == 2
    assert all(r["model_link"] is False for r in doc["pairs"])
    assert len(calls) == 3


def test_run_refuses_replayed_output(live_env, monkeypatch):
    from app.adapters.nightshift import ModelResult, NightshiftClient

    def replay(self, lane, messages, **kw):
        return ModelResult(lane=lane, model="nvidia/nemotron-3-ultra-550b-a55b", routed_model=None,
                           content='{"link": true, "confidence": 1}', receipt_id=None, replayed=True,
                           latency_ms=0, usage={}, raw={})

    monkeypatch.setattr(NightshiftClient, "chat", replay)
    doc = n.run(live_env / "out.json")
    assert doc["stopped_early"] == "3 consecutive failed calls"
    assert doc["failed_calls"] == doc["pairs_scored"] == 2
    assert all("replayed" in r["error"] for r in doc["pairs"])


def test_run_does_not_start_a_case_after_the_stop_time(live_env):
    from datetime import datetime, timezone

    doc = n.run(live_env / "out.json", stop_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
                transport=httpx.MockTransport(lambda r: _reply('{"link": false}')))
    assert doc["stopped_early"] == "stop time reached" and doc["cases_completed"] == 0


def test_stop_at_needs_an_offset():
    with pytest.raises(SystemExit):
        n.main(["run", "--stop-at", "2026-10-27T09:30:00"])
