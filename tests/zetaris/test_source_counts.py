"""q_source_counts and app.dq_status 'zetaris:sources': per-source counts for the console Data sources page (WS3-27)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.adapters.zetaris import NAMED_QUERIES, QueryResult, ZetarisClient
from app.adapters.zetaris_queries_n2 import SOURCE_COUNTS
from app.config import Settings
from app.dq_status import SOURCES_COMPONENT, build_sources_row, run_sources
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]
IDS = [sid for sid, _, _ in SOURCE_COUNTS]


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> ZetarisClient:
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    return ZetarisClient(s, tracer=Tracer("src-test", tmp_path_factory.mktemp("t"), echo=False))


def test_ids_are_the_web_registry_ids():
    """The page keys counts by these ids; they must match apps/web/lib/dataSources.ts exactly."""
    ts = (ROOT / "apps" / "web" / "lib" / "dataSources.ts").read_text(encoding="utf-8")
    web = re.findall(r'^\s*id: "([^"]+)"', ts, flags=re.M)
    assert web and sorted(web) == sorted(IDS)
    assert len(set(IDS)) == len(IDS)


def test_live_sql_counts_every_source_once_ordered_and_fails_fast():
    q = NAMED_QUERIES["q_source_counts"]
    for sid, rel, _ in SOURCE_COUNTS:
        assert f"SELECT '{sid}' AS source, count(*) AS n FROM {rel}" in q.lightning
    assert q.lightning.rstrip().endswith("ORDER BY source")  # D-031
    assert q.timeout_s is not None and q.columns == ("source", "n")
    # A REST table is one JSON response per call: count the items through the feed views instead.
    assert "FROM nexus_feeds." not in q.lightning
    for view in ("nexus.news_items", "nexus.social_posts", "nexus.weather_hourly"):
        assert view in q.lightning


def test_sample_twin_counts_the_bundle_and_leaves_missing_sources_null(client):
    r = client.named("q_source_counts", agent="test")
    assert r.source == "sample"
    got = dict(r.rows)
    assert sorted(got) == sorted(IDS)
    for sid in ("s3csv.anpr_cameras", "s3csv.cctv_cameras", "nexus_feeds.rest_weather"):
        assert got[sid] is None  # not in the bundle: not measured, never 0
    assert got["sb.crimes"] > 0 and got["s3csv.cctns"] > 0 and got["nexus_feeds.rest_news"] > 0


class FakeZ:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def named(self, name, *, agent, **_):
        assert name == "q_source_counts"
        if self.exc:
            raise self.exc
        return self.result


class FakeSb:
    def __init__(self):
        self.upserts = []

    def upsert(self, table, rows, on_conflict):
        self.upserts.append((table, rows, on_conflict))
        return rows


def _result(source="zetaris"):
    return QueryResult(name="q_source_counts", query_id="qid-1", ms=4200, source=source,
                       rows=[["s3csv.cctns", 3000], ["sb.crimes", 14040], ["s3csv.cctv_cameras", None]])


def test_live_answer_becomes_a_live_row_with_counts():
    row, why = build_sources_row(FakeZ(_result()))
    assert why == "ok" and row["component"] == SOURCES_COMPONENT and row["state"] == "live"
    assert row["detail"]["counts"] == {"s3csv.cctns": 3000, "sb.crimes": 14040}
    assert row["detail"]["not_measured"] == "s3csv.cctv_cameras"
    assert row["detail"]["query_id"] == "qid-1" and row["checked_at"]


@pytest.mark.parametrize("z", [FakeZ(_result("sample")), FakeZ(exc=RuntimeError("timeout"))])
def test_sample_or_failure_writes_nothing_so_the_last_good_row_stays(z, tmp_path):
    sb = FakeSb()
    row, why = run_sources(sb, z, Tracer("t", tmp_path, echo=False))
    assert row is None and sb.upserts == [] and why


def test_run_sources_upserts_one_row(tmp_path):
    sb = FakeSb()
    row, _ = run_sources(sb, FakeZ(_result()), Tracer("t", tmp_path, echo=False))
    assert sb.upserts == [("system_status", [row], "component")]
