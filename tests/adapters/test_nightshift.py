"""Nightshift adapter: headers, pinned lanes, R2, tracing, sample-mode replay."""

import json

import httpx
import pytest

from app.adapters.nightshift import (
    LaneNotConfigured,
    NightshiftClient,
    NightshiftError,
    NightshiftUnauthorized,
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
    c = NightshiftClient(settings(), transport=httpx.MockTransport(ok_handler([])))
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


def test_sample_mode_without_fixture_fails_instead_of_inventing(tmp_path):
    c = NightshiftClient(settings(sample_mode=True), transport=httpx.MockTransport(down), fixtures_dir=tmp_path)
    with pytest.raises(NightshiftError):
        c.chat("fast", [{"role": "user", "content": "never recorded"}], agent="t")
