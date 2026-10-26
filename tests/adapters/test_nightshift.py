"""Nightshift adapter: headers, pinned lanes, R2, tracing, sample-mode replay."""

import json

import httpx
import pytest

from app.adapters.nightshift import (
    LaneNotConfigured,
    NightshiftClient,
    NightshiftError,
    NightshiftUnauthorized,
    fixture_key,
)
from app.config import Settings
from app.tracing import Tracer


def settings(**kw):
    base = dict(
        meterless_base_url="http://ns.test/v1",
        meterless_runtime_token="tok-test",
        lane_fast="nvidia/nemotron-3.5-lightning-30b-a3b",
        lane_reason="nvidia/nemotron-3-super-120b-a12b",
        sample_mode=False,
    )
    base.update(kw)
    return Settings(_env_file=None, **base)


def ok_handler(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={"id": "chatcmpl-1", "model": body["model"], "choices": [{"message": {"content": "OK"}}]},
            headers={"meterless-receipt-id": "ns_rcpt_1"},
        )

    return handler


def down(request):
    raise httpx.ConnectError("down")


def test_chat_sends_pinned_model_and_meterless_headers(tmp_path):
    seen = []
    tracer = Tracer("t1", tmp_path, echo=False)
    c = NightshiftClient(settings(), tracer, transport=httpx.MockTransport(ok_handler(seen)))
    r = c.chat("fast", [{"role": "user", "content": "hi"}], agent="Extractor")

    req = seen[0]
    assert req.url.path == "/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer tok-test"
    assert req.headers["meterless-app"] == "nexus-chennai"
    assert req.headers["meterless-scope"] == "user"
    assert json.loads(req.content)["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert r.routed_model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert r.receipt_id == "ns_rcpt_1"
    assert not r.replayed

    (event,) = tracer.read()
    assert event["action"] == "model_call"
    assert event["agent_name"] == "Extractor"
    assert event["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert event["routed_model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"


def test_meterless_auto_is_refused():
    c = NightshiftClient(settings(lane_fast="meterless/auto"), transport=httpx.MockTransport(ok_handler([])))
    with pytest.raises(LaneNotConfigured):
        c.chat("fast", [{"role": "user", "content": "x"}], agent="t")


def test_unconfigured_lane_is_refused():
    c = NightshiftClient(settings(lane_vision=""), transport=httpx.MockTransport(ok_handler([])))
    with pytest.raises(LaneNotConfigured):
        c.chat("vision", [{"role": "user", "content": "x"}], agent="t")


def test_unauthorized_is_reported():
    c = NightshiftClient(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(NightshiftError) as exc:
        c.chat("fast", [{"role": "user", "content": "x"}], agent="t")
    assert isinstance(exc.value.__cause__, NightshiftUnauthorized)


def test_sample_mode_replays_recorded_fixture(tmp_path):
    msgs = [{"role": "user", "content": "extract"}]
    live = NightshiftClient(
        settings(), transport=httpx.MockTransport(ok_handler([])), fixtures_dir=tmp_path, record_fixtures=True
    )
    live.chat("fast", msgs, agent="Extractor")

    tracer = Tracer("t2", tmp_path / "logs", echo=False)
    offline = NightshiftClient(
        settings(sample_mode=True), tracer, transport=httpx.MockTransport(down), fixtures_dir=tmp_path
    )
    r = offline.chat("fast", msgs, agent="Extractor")
    assert r.replayed and r.content == "OK"
    assert tracer.read()[-1]["status"] == "replayed"


def test_sample_mode_does_not_hide_a_rejected_model(tmp_path):
    # A 400 (e.g. Nightshift does not accept the pinned id) must surface, not be replayed.
    c = NightshiftClient(
        settings(sample_mode=True), transport=httpx.MockTransport(lambda r: httpx.Response(400)), fixtures_dir=tmp_path
    )
    with pytest.raises(NightshiftError):
        c.chat("fast", [{"role": "user", "content": "x"}], agent="t")


def test_sample_mode_without_fixture_fails_instead_of_inventing(tmp_path):
    c = NightshiftClient(settings(sample_mode=True), transport=httpx.MockTransport(down), fixtures_dir=tmp_path)
    with pytest.raises(NightshiftError):
        c.chat("fast", [{"role": "user", "content": "never recorded"}], agent="t")


def test_default_lanes_are_the_pinned_d017_models():
    s = Settings(_env_file=None)
    assert s.lanes["fast"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert s.lanes["reason"] == "nvidia/nemotron-3-ultra-550b-a55b"
    assert "meterless/auto" not in s.lanes.values()


def test_no_token_sends_no_authorization_header():
    seen = []
    c = NightshiftClient(settings(meterless_runtime_token=""), transport=httpx.MockTransport(ok_handler(seen)))
    c.chat("fast", [{"role": "user", "content": "x"}], agent="t")
    assert "authorization" not in {k.lower() for k in seen[0].headers}


def test_sample_mode_without_token_replays_without_calling(tmp_path):
    calls = []
    msgs = [{"role": "user", "content": "x"}]
    rec = NightshiftClient(settings(), transport=httpx.MockTransport(ok_handler([])), fixtures_dir=tmp_path, record_fixtures=True)
    rec.chat("fast", msgs, agent="t")  # records a fixture
    c = NightshiftClient(
        settings(meterless_runtime_token="", sample_mode=True),
        transport=httpx.MockTransport(ok_handler(calls)),
        fixtures_dir=tmp_path,
    )
    result = c.chat("fast", msgs, agent="t")
    assert result.replayed is True and result.content == "OK"
    assert calls == []  # nothing was sent


def test_repeated_identical_requests_record_and_replay_in_order(tmp_path):
    """Judge replay (example 2): the Skeptic asked the same question in round 1 and round 2 and got different
    answers; one fixture per key kept only the last, so replay diverged. The n-th identical request is now
    recorded as <key>-n.json (the first stays <key>.json) and replayed in the same order."""
    answers = iter(["first", "second"])

    def handler(req):
        body = json.loads(req.content)
        return httpx.Response(200, json={"id": "c", "model": body["model"],
                                         "choices": [{"message": {"content": next(answers)}, "finish_reason": "stop"}]})

    msgs = [{"role": "user", "content": "same question"}]
    rec = NightshiftClient(settings(), transport=httpx.MockTransport(handler), fixtures_dir=tmp_path, record_fixtures=True)
    assert [rec.chat("fast", msgs, agent="t").content for _ in range(2)] == ["first", "second"]
    key = fixture_key("fast", msgs)
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"{key}-2.json", f"{key}.json"]

    replay = NightshiftClient(settings(meterless_runtime_token="", sample_mode=True), fixtures_dir=tmp_path)
    assert [replay.chat("fast", msgs, agent="t").content for _ in range(2)] == ["first", "second"]
    with pytest.raises(NightshiftError):
        replay.chat("fast", msgs, agent="t")  # a third ask was never recorded: fail, never reuse an answer
