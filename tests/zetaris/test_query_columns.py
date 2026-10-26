"""Named queries declare their columns; results expose them by name (nexus-3 interface)."""

import httpx
import pytest

from app.adapters.zetaris import NAMED_QUERIES, NamedQuery, QueryResult, ZetarisClient, ZetarisError
from app.config import Settings


def client(rows, registry=None):
    s = Settings(_env_file=None, zetaris_rest_url="http://z.test/api/v1.0", zetaris_api_key="k", zetaris_org_id="1")
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": rows}))
    return ZetarisClient(s, transport=t, registry=registry)


def test_every_registered_query_declares_columns():
    assert all(q.columns for q in NAMED_QUERIES.values())


def test_dicts_use_declared_columns():
    reg = {"q_x": NamedQuery("q_x", "SELECT a, b", "SELECT a, b", "", ("crime_id", "station_id"))}
    r = client([["CHN-1", "PS-A"], ["CHN-2", "PS-B"]], reg).named("q_x", agent="Planner")
    assert r.columns == ("crime_id", "station_id")
    assert r.dicts() == [{"crime_id": "CHN-1", "station_id": "PS-A"}, {"crime_id": "CHN-2", "station_id": "PS-B"}]


def test_width_mismatch_raises():
    reg = {"q_x": NamedQuery("q_x", "SELECT a", "SELECT a", "", ("crime_id", "station_id"))}
    with pytest.raises(ZetarisError, match="declared 2"):
        client([["CHN-1"]], reg).named("q_x", agent="Planner")


def test_dicts_without_columns_raises():
    with pytest.raises(ZetarisError):
        QueryResult(name="q", query_id="1", rows=[[1]], ms=0, source="sample").dicts()


def test_sample_mode_carries_columns():
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    r = ZetarisClient(s).named("q_ping", agent="x")
    assert r.source == "sample" and r.dicts() == [{"one": 1}]
