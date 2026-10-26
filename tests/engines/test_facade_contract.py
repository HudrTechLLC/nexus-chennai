"""LANES.md section 2: exact facade signatures, return shapes, one trace event per call."""

import inspect

from app.engines import ENGINE_NAMES, hmem, markovian, scout_intent, world_model
from app.tracing import EVENT_FIELDS

from .conftest import events

PAIR = {"a": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "red Pulsar"},
        "b": {"crime_type": "chain snatching", "area": "Velachery", "vehicle": "red Pulsar"}}


def _params(fn):
    return [p.name for p in inspect.signature(fn).parameters.values()
            if p.default is inspect.Parameter.empty and p.kind != p.KEYWORD_ONLY]


def test_signatures_match_lanes_contract():
    assert _params(world_model.ingest) == ["entities", "source"]
    assert _params(world_model.context) == ["crime_ids"]
    assert _params(hmem.adjust) == ["pair"]
    assert _params(hmem.record_decision) == ["alert_id", "decision", "reason_code", "note", "pair"]
    assert _params(markovian.dossier) == ["series_id", "records"]
    assert _params(scout_intent.classify) == ["text", "kind"]


def test_every_call_emits_one_trace_event_with_engine(tracer):
    world_model.ingest([{"type": "crime", "key": "C-1"}], source="test")
    world_model.context(["C-1"])
    hmem.adjust(PAIR)
    hmem.record_decision("LA-1", "approve", None, None, PAIR)
    markovian.dossier("S-1", [{"id": "C-1", "kind": "fir", "text": "Chain snatched."}])
    scout_intent.classify("how many thefts last week", "query")
    evs = events(tracer)
    assert [e["engine"] for e in evs] == ["world_model", "world_model", "hmem", "hmem", "markovian", "scout_intent"]
    assert [e["action"] for e in evs] == ["ingest", "context", "adjust", "record_decision", "dossier", "classify"]
    for e in evs:
        assert set(EVENT_FIELDS) <= set(e) and e["engine"] in ENGINE_NAMES and e["agent_name"] == "Engines"


def test_return_shapes():
    ids = world_model.ingest([{"type": "crime", "key": "C-1"}], source="test")
    assert isinstance(ids, list) and all(isinstance(i, str) for i in ids)
    assert {"entities", "relations", "provenance"} <= set(world_model.context(["C-1"]))
    adj = hmem.adjust(PAIR)
    assert set(adj) >= {"delta", "memory_ids", "reason"} and isinstance(adj["delta"], float)
    assert hmem.record_decision("LA-1", "reject", "other", "note", PAIR) is None
    d = markovian.dossier("S-1", [{"id": "C-1", "text": "x"}])
    assert set(d) >= {"text", "cited_ids", "chunks", "tokens_projected", "tokens_actual"}
    r = scout_intent.classify("hello", "tip")
    assert set(r) >= {"route", "intent", "risk", "action"} and r["action"] in ("clean", "quarantine", "urgent")


def test_trace_never_contains_tip_text(tracer):
    secret = "my neighbour Ravi Kumar sells stolen chains at 9876543210"
    scout_intent.classify(secret, "tip")
    raw = tracer.path.read_text(encoding="utf-8")
    assert "Ravi" not in raw and "9876543210" not in raw


def test_hmem_delta_clamped_even_with_many_memories():
    for i in range(12):
        hmem.record_decision(f"LA-{i}", "approve", "same_offender", "same red Pulsar rider", PAIR)
    adj = hmem.adjust(PAIR)
    assert adj["raw_delta"] > hmem.MAX_DELTA  # the raw sum exceeds the cap ...
    assert adj["delta"] == hmem.MAX_DELTA     # ... and the clamp holds
