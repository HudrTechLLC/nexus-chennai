"""q_dq_summary and app.dq_status: data-quality counts for the System page (D-029)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.zetaris import NAMED_QUERIES, QueryResult, ZetarisClient, ZetarisError
from app.adapters.zetaris_queries_n1 import DQ_RULE_VIEWS
from app.config import Settings
from app.dq_status import COMPONENT, build_row, run
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]
RULES = [r for r, _ in DQ_RULE_VIEWS]


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> ZetarisClient:
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    return ZetarisClient(s, tracer=Tracer("dq-test", tmp_path_factory.mktemp("t"), echo=False))


def test_live_sql_counts_every_rule_view_in_20_dq_and_is_ordered():
    q = NAMED_QUERIES["q_dq_summary"]
    dq_sql = (ROOT / "zetaris" / "20_dq.sql").read_text(encoding="utf-8")
    for _, view in DQ_RULE_VIEWS:
        assert f"nexus.{view}" in q.lightning
        assert f"SCHEMASTORE VIEW {view} " in dq_sql
    assert q.lightning.rstrip().endswith("ORDER BY rule")  # D-031
    assert q.timeout_s is not None and q.columns == ("rule", "rows")


def test_sample_twin_measures_six_rules_and_leaves_stale_camera_null(client):
    r = client.named("q_dq_summary", agent="test")
    assert r.source == "sample"
    got = dict(r.rows)
    assert sorted(got) == sorted(RULES)
    assert got["stale_camera"] is None  # the bundle has no camera registry: not measured, not 0
    assert all(isinstance(got[k], int) for k in RULES if k != "stale_camera")
    assert got["duplicate_fir"] > 0 and got["unmapped_section"] > 0  # the bundle plants both


class FakeSb:
    def __init__(self, rows=None):
        self.rows, self.upserts = rows or [], []

    def select(self, table, params=None):
        return self.rows

    def upsert(self, table, rows, on_conflict):
        self.upserts.append((table, rows, on_conflict))
        return rows


class FakeZ:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def named(self, name, *, agent, **_):
        assert name == "q_dq_summary"
        if self.exc:
            raise self.exc
        return self.result


def _live(**counts):
    rows = [[k, v] for k, v in sorted(counts.items())]
    return QueryResult("q_dq_summary", "qid-1", rows, 81000, "zetaris", ("rule", "rows"))


def test_live_row_has_counts_total_and_query_id(tmp_path):
    sb = FakeSb()
    row = run(None, sb, FakeZ(_live(bad_geo=5, duplicate_fir=30, stale_camera=134)), Tracer("t", tmp_path, echo=False))
    assert sb.upserts == [("system_status", [row], "component")]
    assert row["component"] == COMPONENT and row["state"] == "live"
    d = row["detail"]
    assert (d["bad_geo"], d["duplicate_fir"], d["stale_camera"], d["total"]) == (5, 30, 134, 169)
    assert d["query_id"] == "qid-1" and "not_measured" not in d


def test_sample_row_lists_what_it_did_not_measure():
    r = QueryResult("q_dq_summary", "qid-2", [["bad_geo", 1], ["stale_camera", None]], 5, "sample", ("rule", "rows"))
    row = build_row(FakeZ(r), None)
    assert row["state"] == "sample" and row["detail"]["not_measured"] == "stale_camera"
    assert row["detail"]["total"] == 1


def test_down_keeps_the_last_good_counts():
    prev = {"state": "live", "checked_at": "2026-10-26T20:00:00+05:30",
            "detail": {"bad_geo": 5, "duplicate_fir": 30, "source": "zetaris", "query_id": "old"}}
    row = build_row(FakeZ(exc=ZetarisError("timed out")), prev)
    assert row["state"] == "down" and "timed out" in row["detail"]["error"]
    assert row["detail"]["last_ok"] == {"bad_geo": 5, "duplicate_fir": 30, "source": "zetaris",
                                        "checked_at": "2026-10-26T20:00:00+05:30"}
    again = build_row(FakeZ(exc=ZetarisError("still down")), row)  # a second failure carries it forward
    assert again["detail"]["last_ok"] == row["detail"]["last_ok"]
