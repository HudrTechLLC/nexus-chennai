"""Supabase adapter: additive upsert / select / update (WS2-16), over a mocked transport."""

import json

import httpx
import pytest

from app.adapters.supabase import SupabaseClient, SupabaseError
from app.config import Settings


def client(handler):
    s = Settings(_env_file=None, supabase_url="https://sb.test", supabase_service_role_key="svc-test")
    return SupabaseClient(s, transport=httpx.MockTransport(handler))


def test_upsert_uses_merge_duplicates_and_on_conflict():
    seen = []

    def h(req):
        seen.append(req)
        return httpx.Response(201, json=json.loads(req.content))

    out = client(h).upsert("link_alerts", [{"alert_id": "LA-1"}], on_conflict="alert_id")
    req = seen[0]
    assert req.method == "POST" and req.url.path == "/rest/v1/link_alerts"
    assert req.url.params["on_conflict"] == "alert_id"
    assert "resolution=merge-duplicates" in req.headers["prefer"]
    assert req.headers["apikey"] == "svc-test" and out == [{"alert_id": "LA-1"}]


def test_select_passes_filters():
    def h(req):
        assert req.method == "GET" and req.url.params["processed_at"] == "is.null"
        return httpx.Response(200, json=[{"decision_id": 1}])

    assert client(h).select("alert_decisions", {"select": "*", "processed_at": "is.null"}) == [{"decision_id": 1}]


def test_update_requires_a_filter():
    def h(req):
        assert req.method == "PATCH" and req.url.params["alert_id"] == "eq.LA-1"
        return httpx.Response(200, json=[{"alert_id": "LA-1", "status": "approved"}])

    c = client(h)
    assert c.update("link_alerts", {"alert_id": "eq.LA-1"}, {"status": "approved"})[0]["status"] == "approved"
    with pytest.raises(SupabaseError):
        c.update("link_alerts", {}, {"status": "approved"})


def test_errors_surface():
    c = client(lambda req: httpx.Response(400, text="bad"))
    for call in (lambda: c.select("tips"), lambda: c.upsert("tips", {}, "tip_id"),
                 lambda: c.update("tips", {"tip_id": "eq.1"}, {})):
        with pytest.raises(SupabaseError):
            call()


def test_unconfigured_refuses():
    c = SupabaseClient(Settings(_env_file=None, supabase_url="", supabase_service_role_key=""))
    with pytest.raises(SupabaseError):
        c.select("tips")
