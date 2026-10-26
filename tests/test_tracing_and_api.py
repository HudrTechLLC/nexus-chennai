"""Trace schema (D3.12), city pack loading and the /run contract while P4 is pending."""

import pytest
from fastapi.testclient import TestClient

from app.config import load_city
from app.main import app
from app.tracing import EVENT_FIELDS, Tracer


def test_trace_events_have_full_schema(tmp_path):
    t = Tracer("r1", tmp_path, echo=False)
    t.emit("Skeptic", "strike_factor", confidence=0.9)
    (e,) = t.read()
    assert set(EVENT_FIELDS) <= set(e)
    assert e["run_id"] == "r1" and e["zetaris_query_ids"] == []


def test_trace_rejects_unknown_fields(tmp_path):
    with pytest.raises(ValueError):
        Tracer("r2", tmp_path, echo=False).emit("a", "b", made_up=1)


def test_chennai_city_pack_loads():
    city = load_city("chennai")
    assert city["name"] == "Chennai" and city["synthetic"] is True


def test_secret_can_be_read_from_file(tmp_path):
    from app.config import Settings

    f = tmp_path / "key.txt"
    f.write_text("from-file\r\n", encoding="utf-8")
    s = Settings(_env_file=None, supabase_service_role_key="inline", supabase_service_role_key_file=str(f))
    assert s.supabase_service_role_key == "from-file"


def test_run_is_honest_until_graph_exists():
    resp = TestClient(app).post("/run", json={"input": {"kind": "case"}})
    assert resp.status_code == 501
    assert resp.json()["detail"]["status"] == "not_implemented"
