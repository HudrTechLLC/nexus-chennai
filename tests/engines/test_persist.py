"""Engines write-through to Supabase (0005, D-020), with a mocked transport: no network."""

import json

import httpx
import pytest

from app.engines import _persist, hmem, world_model

from .conftest import CLOCK

PAIR = {"a": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "motorcycle"},
        "b": {"crime_type": "chain snatching", "area": "Adyar", "vehicle": "car"}}


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"table": request.url.path.rsplit("/", 1)[-1], "on_conflict": request.url.params["on_conflict"],
                      "prefer": request.headers["prefer"], "rows": json.loads(request.content)})
        return httpx.Response(201)

    monkeypatch.setenv("ENGINES_PERSIST", "supabase")
    _persist.set_client(httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler)))
    _persist.reset()
    yield calls
    _persist.set_client(None)
    _persist.reset()


def test_off_by_default_sends_nothing(monkeypatch):
    monkeypatch.delenv("ENGINES_PERSIST", raising=False)
    _persist.set_client(httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("network call"))))
    try:
        world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}], "Extractor")
        hmem.record_decision("LA-1", "reject", "x", None, PAIR)
    finally:
        _persist.set_client(None)


def test_world_model_ingest_writes_entities_edges_and_observations(captured):
    world_model.ingest([{"type": "crime", "key": "CHN-1", "edges": [
        {"type": "used_vehicle", "to": {"type": "vehicle", "key": "TN 09 AB 1234"}}]}], "Extractor")
    by = {c["table"]: c for c in captured}
    assert set(by) == {"wm_entities", "wm_edges", "wm_observations"}
    assert {r["id"] for r in by["wm_entities"]["rows"]} == {"crime:fir:CHN-1", "vehicle:plate:TN09AB1234"}
    (edge,) = by["wm_edges"]["rows"]
    assert edge["crime_id"] == "CHN-1" and edge["type"] == "used_vehicle"
    assert by["wm_entities"]["prefer"].startswith("resolution=merge-duplicates")
    assert by["wm_observations"]["prefer"].startswith("resolution=ignore-duplicates")  # append-only table
    assert all(r["synthetic"] is True for c in captured for r in c["rows"])
    assert {r["source"] for r in by["wm_observations"]["rows"]} == {"Extractor"}


def test_hmem_decision_writes_memory_and_new_ledger_lines_once(captured, tmp_path):
    hmem.configure(tmp_path / "m", clock=CLOCK)
    hmem.record_decision("LA-7", "reject", "different_offenders", "one used a car", PAIR)
    mem = [c for c in captured if c["table"] == "hmem_memories"][-1]["rows"]
    (row,) = mem
    assert row["id"] == "nexus:mem-1" and row["alert_id"] == "LA-7" and row["polarity"] == -1
    assert row["reason_code"] == "different_offenders" and row["note"] == "one used a car"
    first = [c for c in captured if c["table"] == "hmem_ledger"][-1]
    assert first["on_conflict"] == "entry_hash" and first["prefer"].startswith("resolution=ignore-duplicates")
    sent = {r["entry_hash"] for r in first["rows"]}
    hmem.adjust(PAIR)  # adds a "read" ledger line
    hmem.record_decision("LA-8", "approve", "same_offender", None, PAIR)
    second = [c for c in captured if c["table"] == "hmem_ledger"][-1]
    assert sent.isdisjoint({r["entry_hash"] for r in second["rows"]})  # only new lines are sent
    assert {r["action"] for r in second["rows"]} >= {"read", "create"}


def test_persist_failure_is_traced_and_raised(monkeypatch, tracer):
    monkeypatch.setenv("ENGINES_PERSIST", "supabase")
    _persist.set_client(httpx.Client(base_url="https://example.invalid",
                                     transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))))
    try:
        with pytest.raises(RuntimeError):
            world_model.ingest([{"type": "vehicle", "key": "TN09AB1234"}], "Extractor")
    finally:
        _persist.set_client(None)
    ev = [e for e in tracer.read() if e["action"] == "persist"][-1]
    assert ev["status"] == "error" and ev["engine"] == "world_model"
