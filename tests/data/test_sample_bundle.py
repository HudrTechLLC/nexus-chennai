"""The committed sample bundle (WS1-11) works through the real sample-mode path (spec P1 exit:
every named query returns rows in sample mode), for the three judge cases."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from app.adapters.zetaris import ZetarisClient
from app.config import Settings
from app.tracing import Tracer
from data.generator.sample import JUDGE_IDS, SCHEMAS, UNIFIED_COLUMNS

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample"


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> ZetarisClient:
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    assert s.sample_dir == SAMPLE
    return ZetarisClient(s, tracer=Tracer("sample-test", tmp_path_factory.mktemp("t"), echo=False))


def test_every_table_the_twins_open_exists_with_the_supabase_shape():
    con = duckdb.connect()
    for table, cols in SCHEMAS.items():
        got = con.execute(f"DESCRIBE SELECT * FROM '{(SAMPLE / 'sb' / f'{table}.parquet').as_posix()}'").fetchall()
        assert [r[0] for r in got] == [c for c, _ in cols], table
    for f in ("ref/place_aliases.csv", "ref/calendar.csv", "ref/osm_pois.parquet", "views.sql", "_truth/pairs.csv"):
        assert (SAMPLE / f).is_file(), f


def test_bundle_is_small_and_synthetic():
    size = sum(p.stat().st_size for p in SAMPLE.rglob("*") if p.is_file())
    assert size < 5 * 1024 * 1024
    con = duckdb.connect()
    for table in ("crimes", "statements", "crime_vehicles", "tips", "crime_features"):
        p = (SAMPLE / "sb" / f"{table}.parquet").as_posix()
        assert con.execute(f"SELECT count(*) FROM '{p}' WHERE synthetic IS NOT TRUE").fetchone()[0] == 0, table


@pytest.mark.parametrize("crime_id", JUDGE_IDS)
def test_q_case_and_q_candidates_for_each_judge_case(client, crime_id):
    case = client.named("q_case", agent="test", crime_id=crime_id)
    assert case.source == "sample" and len(case.rows) == 1
    cands = client.named("q_candidates", agent="test", crime_id=crime_id, days=45, ring=6)
    assert cands.rows


def test_red_pulsar_members_in_window_are_candidates(client):
    series = json.loads((SAMPLE / "_truth" / "series.json").read_text(encoding="utf-8"))
    red = next(s for s in series if s["series_id"] == "SER-RED-PULSAR")
    got = {r["crime_id"] for r in client.named("q_candidates", agent="test", crime_id=JUDGE_IDS[0],
                                                 days=45, ring=6).dicts()}
    assert len(set(red["crime_ids"]) & got) >= 2


def test_v_crime_unified_view_and_hotspot_input(client):
    cols = client._duck.execute("DESCRIBE v_crime_unified").fetchall()
    assert [c[0] for c in cols] == UNIFIED_COLUMNS
    hex_rows = client.named("q_hex_counts", agent="test", baseline_since="2026-08-01", until="2026-10-26")
    assert hex_rows.rows


def test_dq_flags_find_every_planted_kind(client):
    dq = json.loads((SAMPLE / "_truth" / "dq.json").read_text(encoding="utf-8"))
    dups = json.loads((SAMPLE / "_truth" / "duplicates.json").read_text(encoding="utf-8"))
    ids = ",".join([r["row_id"] for r in dq] + [i for d in dups for i in d["crime_ids"]])
    rules = {r[1] for r in client.named("q_dq_flags", agent="test", ids=ids).rows}
    assert {"duplicate_fir", "bad_geo", "time_inconsistent"} <= rules


def test_tips_are_unscreened():
    p = (SAMPLE / "sb" / "tips.parquet").as_posix()
    n, unscreened = duckdb.connect().execute(
        f"SELECT count(*), count(*) FILTER (WHERE guard IS NULL AND status = 'new') FROM '{p}'").fetchone()
    assert n == 40 and unscreened == 40
