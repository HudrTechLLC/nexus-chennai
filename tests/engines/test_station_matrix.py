"""q_station_matrix (spec E5 v_station_link_matrix): approved alerts aggregated station x station."""

import duckdb

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient, render
from app.adapters.zetaris_queries_n2 import MATRIX_COLUMNS
from app.config import Settings
from app.tracing import Tracer

# stations as the JDBC '{a,b}' string form (A1-A5) and as a real list (L1): the twin accepts both.
ALERTS = """SELECT * FROM (VALUES
 ('A1', '{PS-A,PS-B}', 'approved', '2026-10-20T10:00:00+05:30'),
 ('A2', '{PS-B,PS-A}', 'approved', '2026-10-21T10:00:00+05:30'),
 ('A3', '{PS-A,PS-B,PS-C}', 'approved', '2026-10-22T10:00:00+05:30'),
 ('A4', '{PS-A}', 'approved', '2026-10-22T11:00:00+05:30'),
 ('A5', '{PS-A,PS-B}', 'rejected', '2026-10-22T12:00:00+05:30'),
 ('A6', '{PS-C,PS-D}', 'approved', '2026-10-01T00:30:00+05:30')
) t(alert_id, stations, status, created_at)"""


def _client(tmp_path, sql):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    duckdb.connect().execute(f"COPY ({sql}) TO '{(d / 'sb' / 'link_alerts.parquet').as_posix()}' (FORMAT PARQUET)")
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False))
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{d.as_posix()}'")
    return c


def _matrix(c, since="", until=""):
    res = c.named("q_station_matrix", agent="Console", since=since, until=until)
    assert res.columns == MATRIX_COLUMNS
    return {(r["station_a"], r["station_b"]): (r["approved_links"], r["cross_station"], r["alert_ids"])
            for r in res.dicts()}


def test_approved_alerts_count_once_per_station_pair(tmp_path):
    m = _matrix(_client(tmp_path, ALERTS))
    assert m[("PS-A", "PS-B")] == (3, True, "A1,A2,A3")      # order inside the alert does not matter
    assert m[("PS-A", "PS-C")] == (1, True, "A3") and m[("PS-B", "PS-C")] == (1, True, "A3")
    assert m[("PS-A", "PS-A")] == (1, False, "A4")           # single-station alert on the diagonal
    assert ("PS-B", "PS-A") not in m and ("PS-B", "PS-B") not in m   # no mirror, no diagonal for multi-station
    assert all("A5" not in v[2] for v in m.values())          # rejected never counts


def test_range_is_city_local(tmp_path):
    c = _client(tmp_path, ALERTS)
    assert set(_matrix(c, since="2026-10-01", until="2026-10-02")) == {("PS-C", "PS-D")}  # 00:30 IST on the 1st
    assert set(_matrix(c, since="2026-10-22")) == {("PS-A", "PS-B"), ("PS-A", "PS-C"), ("PS-B", "PS-C"),
                                                  ("PS-A", "PS-A")}


def test_stations_as_a_real_list(tmp_path):
    sql = """SELECT * FROM (VALUES ('L1', ['PS-X', 'PS-Y'], 'approved', '2026-10-20T10:00:00+05:30'))
             t(alert_id, stations, status, created_at)"""
    assert _matrix(_client(tmp_path, sql)) == {("PS-X", "PS-Y"): (1, True, "L1")}


def test_lightning_renders_with_only_declared_params():
    sql = render(NAMED_QUERIES["q_station_matrix"].lightning, {"since": "2026-10-20", "until": ""})
    assert "sb.link_alerts" in sql and "status = 'approved'" in sql and "\\" not in sql
    assert "explode" in sql and "Asia/Kolkata" in sql
