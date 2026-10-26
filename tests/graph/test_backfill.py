"""Extractor backfill (resumable JSONL + store) and the thinking-off switch for structured calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from agents_fixtures import ADYAR, VELACHERY, FakeNightshift, FakeZetaris, default_handlers  # noqa: E402

from app.agents import AgentDeps, MemoryStore  # noqa: E402
from app.agents.base import chat_json  # noqa: E402
from app.graph.backfill import Backfill, done_ids  # noqa: E402
from app.tracing import Tracer  # noqa: E402

MODEL_MO = {"mo": {"approach": "two_wheeler_from_behind", "offender_count": 2, "target": "lone_pedestrian_woman",
                   "target_item": "gold_chain", "escape": "two_wheeler", "violence": "push", "time_band": "evening",
                   "place_type": ["bus_stop"], "disguise": ["helmet"], "verbal": None},
            "visual_tags": [], "entities": {"plates": [], "persons": [], "phones": []}}


@pytest.fixture
def make_deps(tmp_path):
    def _make(responder):
        return AgentDeps(tracer=Tracer("test_run", tmp_path, echo=False), zetaris=FakeZetaris(default_handlers()),
                         nightshift=FakeNightshift(responder), store=MemoryStore())
    return _make


def _capture(deps):
    seen = []
    orig = deps.nightshift.chat

    def chat(lane, messages, *, agent, purpose="", **params):
        seen.append(params)
        return orig(lane, messages, agent=agent, purpose=purpose, **params)

    deps.nightshift.chat = chat
    return seen


def test_chat_json_thinking_off_sets_template_kwargs(make_deps):
    deps = make_deps(lambda lane, m, p: '{"ok": true}')
    seen = _capture(deps)
    chat_json(deps, "fast", [{"role": "user", "content": "x"}], agent="T", purpose="p", thinking=False)
    chat_json(deps, "fast", [{"role": "user", "content": "x"}], agent="T", purpose="p")
    assert seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in seen[1]


def _backfill(deps, path):
    return Backfill(None, path, store=deps.store, zetaris=deps.zetaris, nightshift=deps.nightshift,  # type: ignore[arg-type]
                    tracer=deps.tracer)


def test_backfill_writes_store_and_jsonl_then_resumes(make_deps, tmp_path):
    deps = make_deps(lambda lane, m, p: json.dumps(MODEL_MO))
    seen = _capture(deps)
    path = tmp_path / "crime_features.jsonl"
    ids = [ADYAR["crime_id"], VELACHERY["crime_id"], "CHN-XX-2026-999999"]
    out = _backfill(deps, path).run(ids, concurrency=2)
    assert out["ok"] == 2 and [cid for cid, _ in out["failed"]] == ["CHN-XX-2026-999999"]
    assert done_ids(path) == {ADYAR["crime_id"], VELACHERY["crime_id"]}
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["model"] == "nvidia/test-fast" and rec["receipt_id"] and rec["mo"]
    assert seen and all(p.get("chat_template_kwargs") == {"enable_thinking": False} for p in seen)
    assert set(deps.store.features) == {ADYAR["crime_id"], VELACHERY["crime_id"]}

    again = _backfill(deps, path).run(ids, concurrency=2)
    assert again["skipped"] == 2 and again["ok"] == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_export_jsonl_rebuilds_from_store_after_remap(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_worker_store import FakeSB

    from app.graph.backfill import export_jsonl, stored_ids
    path = tmp_path / "crime_features.jsonl"
    # local file written under the OLD id; Supabase row remapped to the NEW id, same receipt
    path.write_text(json.dumps({"crime_id": "CHN-OLD-1", "receipt_id": "r1", "routed_model": "m-routed",
                                "degraded": ["audio:S1"]}) + "\n", encoding="utf-8")
    sb = FakeSB({"crime_features": [
        {"crime_id": "CHN-NEW-1", "extractor_version": "mo-v3", "model": "m", "receipt_id": "r1", "mo": {"a": 1},
         "visual_tags": [], "entities": {}, "confidence": 0.8, "synthetic": True}]})
    assert export_jsonl(sb, path) == 1
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["crime_id"] == "CHN-NEW-1" and rec["routed_model"] == "m-routed" and rec["degraded"] == ["audio:S1"]
    assert done_ids(path) == {"CHN-NEW-1"} and stored_ids(sb) == {"CHN-NEW-1"}


def test_backfill_skips_ids_already_stored(make_deps, tmp_path):
    deps = make_deps(lambda lane, m, p: json.dumps(MODEL_MO))
    out = _backfill(deps, tmp_path / "f.jsonl").run([ADYAR["crime_id"], VELACHERY["crime_id"]],
                                                     skip_also={ADYAR["crime_id"]})
    assert out["skipped"] == 1 and out["ok"] == 1 and set(deps.store.features) == {VELACHERY["crime_id"]}
