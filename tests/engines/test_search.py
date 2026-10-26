"""q_search (spec E5, SRCH-02/03): text + filters over crimes and statements, re-ranked in code (D-027)."""

import os
from pathlib import Path

import duckdb
import pytest

from app.adapters.zetaris import NAMED_QUERIES, NamedQuery, ZetarisClient, render
from app.adapters.zetaris_queries_n2 import SEARCH_COLUMNS, search_params, search_pattern
from app.config import Settings
from app.engines.similarity import rank_rows
from app.tracing import Tracer

GENERATED = Path(os.environ.get("NEXUS_GENERATED_DIR", "C:/Apps/Nexus-n1-gen/data/generated"))

CRIMES = """SELECT * FROM (VALUES
 ('C1', 'PS-A', 'chain_snatching', 'two_wheeler', '2026-10-10T21:15:00+05:30', 13.0, 80.25, 'LB Road', 'registered', 3,
  'Two men on a red Pulsar snatched a gold chain.'),
 ('C2', 'PS-B', 'chain_snatching', NULL, '2026-10-01T00:30:00+05:30', 13.1, 80.2, 'Anna Nagar', 'closed', 3,
  'Chain snatched near the bus stop.'),
 ('C3', 'PS-A', 'theft', NULL, '2026-10-12T10:00:00+05:30', 13.0, 80.25, 'Adyar', 'registered', 2,
  'Phone stolen from a parked car.'),
 ('C4', 'PS-A', 'house_break', NULL, '2026-10-05T03:00:00+05:30', 13.0, 80.25, 'Besant Nagar', 'registered', 4,
  'Grille cut at the rear window.')
) t(crime_id, station_id, category, sub_type, occurred_from, lat, lon, address, status, severity, narrative)"""
STATEMENTS = """SELECT * FROM (VALUES ('S1', 'C3', 'He rode off on a red Pulsar.'), ('S2', 'C4', 'Nothing seen.'))
  t(statement_id, crime_id, text)"""


@pytest.fixture
def client(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    con = duckdb.connect()
    con.execute(f"COPY ({CRIMES}) TO '{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY ({STATEMENTS}) TO '{(d / 'sb' / 'statements.parquet').as_posix()}' (FORMAT PARQUET)")
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False))
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{d.as_posix()}'")
    return c


def _search(client, q="", **filters):
    res = client.named("q_search", agent="Search tools", **search_params(q, filters))
    assert res.source == "sample" and res.columns == SEARCH_COLUMNS
    return res.dicts()


def test_text_matches_narrative_and_statements_newest_first(client):
    rows = _search(client, "red Pulsar")
    assert [r["crime_id"] for r in rows] == ["C3", "C1"]          # newest first; C3 only via its statement
    assert {r["crime_id"]: r["matched_in"] for r in rows} == {"C3": "statement", "C1": "crime"}
    assert rows[1]["occurred_from"] == "2026-10-10T21:15:00+05:30"


def test_word_prefix_match_and_no_substring_match(client):
    assert {r["crime_id"] for r in _search(client, "snatch")} == {"C1", "C2"}   # snatch -> snatched / snatching
    assert _search(client, "ear") == []                                         # not inside "near" / "rear"


def test_filters_without_text(client):
    rows = _search(client, "", station_id="PS-A", status="registered")
    assert [r["crime_id"] for r in rows] == ["C3", "C1", "C4"] and {r["matched_in"] for r in rows} == {"filters"}
    assert [r["crime_id"] for r in _search(client, "", category="chain_snatching")] == ["C1", "C2"]


def test_dates_are_city_local(client):
    # C2 is 2026-10-01 00:30 in Chennai (still 30 Sep in UTC): a city-local "since 1 Oct" must include it.
    assert "C2" in {r["crime_id"] for r in _search(client, "", since="2026-10-01", until="2026-10-02")}
    assert [r["crime_id"] for r in _search(client, "", since="2026-10-11")] == ["C3"]


def test_rank_rows_puts_the_best_text_match_first(client):
    ranked = rank_rows("gold chain red pulsar", _search(client, "chain pulsar"))
    assert ranked[0]["crime_id"] == "C1" and ranked[0]["score"] > ranked[-1]["score"]
    assert all(r["score"] is None for r in rank_rows("", _search(client, "", station_id="PS-A")))


def test_pattern_is_safe_for_both_dialects():
    p = search_pattern("Red Pulsar, near Adyar! TN09 4471 ' OR 1=1 --")
    assert "\\" not in p and "'" not in p and ":" not in p
    assert p == "(^|[^a-z0-9])(red|pulsar|adyar|tn09|4471)"  # stopwords and 1-char tokens dropped
    assert search_pattern("the of and") == ""


def test_lightning_renders_with_only_declared_params_and_registered_sources():
    q: NamedQuery = NAMED_QUERIES["q_search"]
    sql = render(q.lightning, search_params("red pulsar", {"station_id": "PS-A", "since": "2026-10-01"}))
    assert "sb.crimes" in sql and "sb.statements" in sql and "rlike" in sql
    assert "from_utc_timestamp" in sql and "to_utc_timestamp" in sql and "\\" not in sql
    assert "'PS-A'" in sql and "Asia/Kolkata" in sql


@pytest.mark.skipif(not (GENERATED / "supabase" / "crimes.jsonl").exists(), reason="nexus-1 generated data not local")
def test_search_on_the_generated_city(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    con = duckdb.connect()
    for t in ("crimes", "statements"):
        src = (GENERATED / "supabase" / f"{t}.jsonl").as_posix()
        con.execute(f"COPY (SELECT * FROM read_json_auto('{src}')) TO '{(d / 'sb' / f'{t}.parquet').as_posix()}'"
                    " (FORMAT PARQUET)")
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False))
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{d.as_posix()}'")
    rows = c.named("q_search", agent="t", limit=5000, **search_params("red pulsar chain", {})).dicts()
    assert rows and all(r["occurred_from"].endswith("+05:30") for r in rows)
    top = rank_rows("red pulsar chain snatching", rows)[:10]
    assert sum("pulsar" in (r["text"] or "").lower() for r in top) >= 5


def test_free_text_console_search_finds_the_pulsar_snatching(client):
    """Live miss (2026-10-26): "red pulsar chain snatching Adyar" returned nothing. q_search itself matches it;
    rank_rows puts the Pulsar chain snatching first."""
    rows = _search(client, "red pulsar chain snatching Adyar")
    assert "C1" in {r["crime_id"] for r in rows}
    assert rank_rows("red pulsar chain snatching Adyar", rows)[0]["crime_id"] == "C1"
