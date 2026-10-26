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


def test_tips_carry_recorded_tip_guard_results_and_no_secrets():
    p = (SAMPLE / "sb" / "tips.parquet").as_posix()
    n, hashed, bad = duckdb.connect().execute(
        f"SELECT count(*), count(tip_code_hash), count(*) FILTER (WHERE (guard IS NULL) <> (status = 'new')) "
        f"FROM '{p}'").fetchone()
    assert n == 40 and hashed == 0 and bad == 0  # screened rows have a verdict, unscreened ones none


def test_hero_cross_station_pair_is_a_candidate(client):
    """Red Pulsar: Velachery-000877 (3.5 km, 2 days later, other station) must be a candidate of Adyar-001182."""
    rows = {r["crime_id"]: r for r in client.named("q_candidates", agent="test", crime_id="CHN-AD-2026-001182",
                                                     days=45, ring=6).dicts()}
    assert "CHN-VL-2026-000877" in rows and rows["CHN-VL-2026-000877"]["same_station"] is False


def test_q_tip_corroboration_in_sample_mode(client):
    rows = client.named("q_tip_corroboration", agent="test", crime_id="CHN-AD-2026-001182").dicts()
    assert all(r["status"] in ("screened", "reviewed", "urgent") for r in rows)


def test_vehicle_trail_ties_the_hero_plate_to_both_scenes(client):
    """Red Pulsar: the partial FIR plate finds TN09BX4471 read near Adyar-001182 and Velachery-000877."""
    rows = client.named("q_vehicle_trail", agent="test", plate_pattern="TN 09 ?? 4471",
                        t0="2026-10-14T19:40:00+05:30", t1="2026-10-14T19:50:00+05:30", cells="").dicts()
    scenes = {r["crime_id"] for r in rows if r["plate_text"] == "TN09BX4471"}
    assert {"CHN-AD-2026-001182", "CHN-VL-2026-000877"} <= scenes
    assert all(r["read_at"].endswith("+05:30") for r in rows)


def test_vehicle_trail_feeds_the_vehicle_factor(client):
    from app.scoring.factors import ANPR_BOTH_SCENES, vehicle

    rows = client.named("q_vehicle_trail", agent="test", plate_pattern="TN09??4471",
                        t0="2026-10-14T19:40:00+05:30", t1="2026-10-16T19:55:00+05:30", cells="").dicts()
    a, b = {"crime_id": "CHN-AD-2026-001182"}, {"crime_id": "CHN-VL-2026-000877"}
    assert vehicle(a, b, rows) == ANPR_BOTH_SCENES


def test_offender_return_ranks_the_planted_offender_first(client):
    truth = json.loads((SAMPLE.parent / "sample" / "_truth" / "series.json").read_text(encoding="utf-8"))
    assert truth  # bundle truth present
    rows = client.named("q_offender_return", agent="test", mo_tags="night_house_break,back_door_pried", ward=5,
                        since="2025-08-19T02:00:00+05:30").dicts()
    top = rows[0]
    assert top["person_ref"] == "P-90001" and top["near_home"] is True and top["mo_overlap"] == 1.0
    assert 0 <= top["days_since_release"] <= 60


def test_calls_near_the_adyar_hero(client):
    rows = client.named("q_calls_near", agent="test", crime_id="CHN-AD-2026-001182").dicts()
    assert any(r["category"] == "chain_snatching" and r["km_from_scene"] <= 1.0 for r in rows)
    assert all(-120 - 10 <= r["minutes_from_start"] for r in rows)
