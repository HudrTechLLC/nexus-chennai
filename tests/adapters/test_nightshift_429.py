"""Nightshift 429: retried with backoff, honouring Retry-After (seconds or HTTP-date, capped); never replayed."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import json

import httpx
import pytest

from app.adapters import nightshift as N
from app.adapters.nightshift import NightshiftClient, NightshiftError, retry_after_seconds
from app.config import Settings


def settings(**kw):
    base = dict(meterless_base_url="http://ns.test/v1", meterless_runtime_token="tok-test",
                lane_fast="nvidia/nemotron-3.5-lightning-30b-a3b", sample_mode=False)
    base.update(kw)
    return Settings(_env_file=None, **base)


def ok_handler(seen):
    def handler(request):
        seen.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={"id": "chatcmpl-1", "model": body["model"],
                                         "choices": [{"message": {"content": "OK"}}]},
                              headers={"meterless-receipt-id": "ns_rcpt_1"})

    return handler


@pytest.fixture
def waits(monkeypatch):
    """Record tenacity's sleeps instead of sleeping (tenacity copies the retrying object per call, keeping sleep)."""
    seen: list[float] = []
    monkeypatch.setattr(NightshiftClient._post.retry, "sleep", seen.append)
    return seen


def limited_then_ok(headers, calls, n_limited=1):
    ok = ok_handler([])

    def handler(request):
        calls.append(request)
        if len(calls) <= n_limited:
            return httpx.Response(429, json={"error": "rate_limited"}, headers=headers)
        return ok(request)

    return handler


def chat(c):
    return c.chat("fast", [{"role": "user", "content": "hi"}], agent="t")


def test_429_then_ok_succeeds_after_honouring_retry_after_seconds(waits):
    calls = []
    c = NightshiftClient(settings(), transport=httpx.MockTransport(limited_then_ok({"Retry-After": "2"}, calls)))
    assert chat(c).content == "OK"
    assert len(calls) == 2 and waits == [2.0]


def test_retry_after_http_date_is_honoured(waits):
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=5), usegmt=True)
    calls = []
    c = NightshiftClient(settings(), transport=httpx.MockTransport(limited_then_ok({"Retry-After": when}, calls)))
    assert chat(c).content == "OK"
    assert len(waits) == 1 and 3.0 <= waits[0] <= 5.0


def test_retry_after_is_capped(waits):
    calls = []
    c = NightshiftClient(settings(), transport=httpx.MockTransport(limited_then_ok({"Retry-After": "3600"}, calls)))
    chat(c)
    assert waits == [N.RETRY_AFTER_CAP_SECONDS]


def test_429_without_retry_after_uses_exponential_backoff(waits):
    calls = []
    c = NightshiftClient(settings(), transport=httpx.MockTransport(limited_then_ok({}, calls, n_limited=2)))
    assert chat(c).content == "OK"
    assert len(calls) == 3 and waits == [0.5, 1.0]


def test_persistent_429_gives_up_after_three_attempts(waits):
    calls = []
    c = NightshiftClient(settings(), transport=httpx.MockTransport(limited_then_ok({"Retry-After": "1"}, calls, 99)))
    with pytest.raises(NightshiftError, match="429"):
        chat(c)
    assert len(calls) == 3 and waits == [1.0, 1.0]


def test_sample_mode_does_not_replay_a_429(waits, tmp_path):
    """Rate-limited is not an outage: a live 429 must surface, not be swapped for a recorded fixture."""
    rec = NightshiftClient(settings(), transport=httpx.MockTransport(ok_handler([])), fixtures_dir=tmp_path,
                           record_fixtures=True)
    chat(rec)  # a fixture exists for this exact request
    calls = []
    c = NightshiftClient(settings(sample_mode=True), fixtures_dir=tmp_path,
                         transport=httpx.MockTransport(limited_then_ok({}, calls, 99)))
    with pytest.raises(NightshiftError, match="429"):
        chat(c)
    assert len(calls) == 3


def test_other_4xx_is_still_not_retried(waits):
    calls = []

    def bad(request):
        calls.append(request)
        return httpx.Response(400)

    c = NightshiftClient(settings(), transport=httpx.MockTransport(bad))
    with pytest.raises(NightshiftError):
        chat(c)
    assert len(calls) == 1 and waits == []


@pytest.mark.parametrize("raw,want", [("0", 0.0), ("7", 7.0), (" 1.5 ", 1.5), ("-3", 0.0), ("999", 20.0),
                                      (None, None), ("", None), ("soon", None), ("nan", None)])
def test_retry_after_parsing(raw, want):
    assert retry_after_seconds(raw) == want


def test_retry_after_past_date_is_zero():
    past = format_datetime(datetime.now(timezone.utc) - timedelta(minutes=5), usegmt=True)
    assert retry_after_seconds(past) == 0.0
