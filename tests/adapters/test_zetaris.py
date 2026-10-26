"""Zetaris adapter: REST contract, named-query governance, tracing, sample mode."""

import json
import uuid

import httpx
import pytest

from app.adapters.zetaris import UnknownQuery, ZetarisClient, ZetarisError, render
from app.config import Settings
from app.tracing import Tracer


def settings(**kw):
    base = dict(zetaris_rest_url="http://z.test/api/v1.0", zetaris_api_key="key-test", zetaris_org_id="7")
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_named_query_uses_documented_rest_contract(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [["1"]]})

    tracer = Tracer("z1", tmp_path, echo=False)
    r = ZetarisClient(settings(), tracer, transport=httpx.MockTransport(handler)).named("q_ping", agent="Planner")

    req = seen[0]
    assert req.url.path == "/api/v1.0/sql-editor/sqls/run"
    assert req.headers["authorization"] == "Bearer key-test"
    assert req.headers["x-org-id"] == "7"
    uuid.UUID(req.headers["x-request-id"])  # must be a UUID
    body = json.loads(req.content)
    assert body["sql"] == "SELECT 1"
    assert body["source"] == "SqlEditor"
    assert body["queryId"] == r.query_id
    assert r.rows == [["1"]] and r.source == "zetaris"
    (event,) = tracer.read()
    assert event["zetaris_query_ids"] == [r.query_id]
    assert event["agent_name"] == "Planner"


def test_unregistered_query_is_refused():
    with pytest.raises(UnknownQuery):
        ZetarisClient(settings()).named("SELECT * FROM crimes", agent="x")


def test_errors_raise_when_not_in_sample_mode():
    c = ZetarisClient(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(ZetarisError):
        c.named("q_ping", agent="x")


def test_sample_mode_does_not_hide_bad_sql():
    c = ZetarisClient(settings(sample_mode=True), transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    with pytest.raises(ZetarisError):
        c.named("q_ping", agent="x")


def test_sample_mode_falls_back_to_duckdb():
    r = ZetarisClient(settings(sample_mode=True, zetaris_api_key="")).named("q_ping", agent="x")
    assert r.source == "sample" and r.rows == [[1]]


def test_render_escapes_strings_and_rejects_unknown_types():
    assert render("WHERE a = :a AND b = :b", {"a": "O'Brien", "b": 3}) == "WHERE a = 'O''Brien' AND b = 3"
    with pytest.raises(TypeError):
        render(":x", {"x": object()})
    with pytest.raises(KeyError):
        render(":missing", {})


DNS_400 = 'Caused by: java.net.UnknownHostException: aws-0-ap-southeast-1.pooler.supabase.com'


def test_transient_source_400_is_retried_and_traced(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(400, text=DNS_400)
        return httpx.Response(200, json={"data": [["1"]]})

    tracer = Tracer("z2", tmp_path, echo=False)
    r = ZetarisClient(settings(), tracer, transport=httpx.MockTransport(handler)).named("q_ping", agent="Planner")
    assert r.rows == [["1"]] and len(calls) == 2
    (event,) = tracer.read()
    assert event["retry_count"] == 1 and "retries=1" in event["output_summary"]


def test_transient_400_gives_up_after_two_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, text="PSQLException: The connection attempt failed.")

    c = ZetarisClient(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(ZetarisError, match="transient"):
        c.named("q_ping", agent="Planner")
    assert len(calls) == 3


def test_bad_sql_400_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, text="[UNRESOLVED_COLUMN] nope")

    c = ZetarisClient(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(ZetarisError):
        c.named("q_ping", agent="Planner")
    assert len(calls) == 1
