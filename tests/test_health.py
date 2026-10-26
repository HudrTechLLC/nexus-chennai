"""/health answers within 3 s whatever the connectors do (judges and the CI docker job call it first)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import main
from app.config import Settings

BLACKHOLE = "http://10.255.255.1"  # non-routable: connects hang until the client timeout


def _settings(**kw) -> Settings:
    base = dict(_env_file=None, sample_mode=False, zetaris_rest_url=f"{BLACKHOLE}/api/v1.0", zetaris_api_key="k",
                meterless_base_url=f"{BLACKHOLE}:8088/v1", meterless_runtime_token="t",
                supabase_url=BLACKHOLE, supabase_service_role_key="k", lane_fast="m-fast")
    return Settings(**{**base, **kw})


def _timed(client):
    t = time.monotonic()
    r = client.get("/health")
    return r, time.monotonic() - t


def test_health_fast_when_every_service_unreachable(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    r, took = _timed(TestClient(main.app))
    assert r.status_code == 200 and took < 3.0, took
    a = r.json()["adapters"]
    assert {a[k]["state"] for k in ("zetaris", "nightshift", "supabase")} == {"down"}
    assert all(a[k]["error"] for k in a)


def test_health_fast_when_probes_hang(monkeypatch):
    def hang(_s):
        time.sleep(10)

    for name in ("_probe_zetaris", "_probe_nightshift", "_probe_supabase"):
        monkeypatch.setattr(main, name, hang)
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    r, took = _timed(TestClient(main.app))
    assert r.status_code == 200 and took < 3.0, took
    assert all(v["state"] == "down" and v["error"].startswith("TimeoutError") for v in r.json()["adapters"].values())


def test_health_sample_mode_reports_sample(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings(sample_mode=True, zetaris_api_key="",
                                                                supabase_url="", supabase_service_role_key=""))
    r, took = _timed(TestClient(main.app))
    a = r.json()["adapters"]
    assert took < 3.0 and a["zetaris"]["state"] == "sample" and a["nightshift"]["state"] == "sample"
    assert a["supabase"] == {"state": "sample", "error": "NotConfigured"}


def test_health_live_without_supabase_reports_local_store(monkeypatch):
    """WS2-22: live mode with no Supabase keys keeps results in data/local/, which is not an outage."""
    monkeypatch.setattr(main, "get_settings", lambda: _settings(supabase_url="", supabase_service_role_key=""))
    a = TestClient(main.app).get("/health").json()["adapters"]
    assert a["supabase"] == {"state": "not_configured", "store": "local", "detail": "not_configured (local store)"}


def test_health_explicit_memory_store_live_is_still_down(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings(supabase_url="", supabase_service_role_key="",
                                                                nexus_store="memory"))
    a = TestClient(main.app).get("/health").json()["adapters"]
    assert a["supabase"] == {"state": "down", "error": "NotConfigured"}


def test_health_bad_store_config_is_reported(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings(nexus_store="redis"))
    a = TestClient(main.app).get("/health").json()["adapters"]
    assert a["supabase"]["state"] == "down" and a["supabase"]["error"].startswith("BadStoreConfig")
