"""DuckDB twins for nexus-1's crime-side named queries (contracts from nexus-1), run for real on parquet."""

import json
import os
from pathlib import Path

import duckdb
import pytest

from app.adapters.zetaris import NamedQuery, ZetarisClient
from app.adapters.zetaris_queries_n2 import TWINS
from app.config import Settings
from app.tracing import Tracer

GENERATED = Path(os.environ.get("NEXUS_GENERATED_DIR", "C:/Apps/Nexus-n1-gen/data/generated"))

CRIMES = """SELECT * FROM (VALUES
 ('CHN-A-1', 'sb.crimes', 'R1', 'PS-A', '1/2026', 'chain_snatching', NULL, '[{"code": "BNS 304"}]',
  TIMESTAMP '2026-10-01 19:00', NULL, TIMESTAMP '2026-10-01 21:00', 13.0, 80.25, 'near the temple', 170,
  '89a', '88a', 'tf3', '2026-W40', 3, '[{"type": "gold_jewellery"}]', NULL, '[{"count": 2}]', '[]',
  'registered', 'Two men on a red Pulsar.', true),
 ('CHN-A-2', 'sb.crimes', 'R2', 'PS-A', '2/2026', 'theft', NULL, '[]',
  TIMESTAMP '2026-10-02 10:00', NULL, TIMESTAMP '2026-10-02 11:00', 13.0, 80.25, NULL, 170,
  '89a', '88a', 'tf3', '2026-W40', 2, '[]', NULL, '[]', '[]', 'registered', 'Phone stolen.', true)
) t(crime_id, source, source_row_id, station_id, fir_no, category, sub_type, sections, occurred_from, occurred_to,
    reported_at, lat, lon, address, ward_no, h3_r9, h3_r8, geohash7, week, severity, property, weapon,
    offenders_described, victims, status, narrative, synthetic)"""
TABLES = {
    "crimes": CRIMES,
    "crime_vehicles": """SELECT * FROM (VALUES ('CHN-A-1', 'used_by_offender', 'motorcycle', 'TN09??4471',
        'Bajaj Pulsar 150', 'red', true)) t(crime_id, role, vehicle_type, plate_pattern, make_model, colour, synthetic)""",
    "statements": """SELECT * FROM (VALUES
        ('ST-2', 'CHN-A-1', 'W-2 (masked)', 'text', 'Red bike.', TIMESTAMP '2026-10-02 09:00', true),
        ('ST-1', 'CHN-A-1', 'W-1 (masked)', 'text', 'Two men.', TIMESTAMP '2026-10-02 08:00', true))
        t(statement_id, crime_id, witness_ref, mode, text, recorded_at, synthetic)""",
    "evidence_media": """SELECT * FROM (VALUES ('EV-1', 'CHN-A-1', 'cctv_still', 'ev/1.jpg',
        TIMESTAMP '2026-10-01 19:02', 'CAM-1', '{"tags": ["red_bike"]}')) t(evidence_id, crime_id, kind, storage_path,
        captured_at, camera_id, vision)""",
    "forensics": """SELECT * FROM (VALUES ('FO-1', 'CHN-A-1', 'fingerprint', 'FP-77'))
        t(forensic_id, crime_id, kind, match_code)""",
    "crime_features": """SELECT * FROM (VALUES ('CHN-A-1', 'x1', '{"entry": "snatch"}', ['red_bike', 'helmet'],
        '{"vehicles": 1}', 'nvidia/nemotron', 'rc-1', 0.9, NULL)) t(crime_id, extractor_version, mo, visual_tags,
        entities, model, receipt_id, confidence, reviewed_by)""",
}


def _client(sample_dir: Path, tmp_path: Path) -> ZetarisClient:
    registry = {name: NamedQuery(name, "SELECT 1", sql, "twin", cols) for name, (sql, cols) in TWINS.items()}
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False), registry=registry)
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{sample_dir.as_posix()}'")
    return c


@pytest.fixture
def sample(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    con = duckdb.connect()
    for name, sql in TABLES.items():
        con.execute(f"COPY ({sql}) TO '{(d / 'sb' / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)")
    return _client(d, tmp_path)


def test_q_case_returns_one_row_with_nested_lists(sample):
    res = sample.named("q_case", agent="Planner", crime_id="CHN-A-1")
    assert res.source == "sample" and res.columns == TWINS["q_case"][1]
    (row,) = res.dicts()
    assert row["fir_no"] == "1/2026" and row["synthetic"] is True
    assert json.loads(row["vehicles"]) == [{"role": "used_by_offender", "type": "motorcycle", "plate": "TN09??4471",
                                            "make_model": "Bajaj Pulsar 150", "colour": "red"}]
    assert [s["statement_id"] for s in json.loads(row["statements"])] == ["ST-1", "ST-2"]  # ordered
    assert json.loads(row["evidence"])[0]["vision"] == {"tags": ["red_bike"]}
    assert json.loads(row["forensics"]) == [{"forensic_id": "FO-1", "kind": "fingerprint", "match_code": "FP-77"}]
    feats = json.loads(row["features"])
    assert feats["mo"] == {"entry": "snatch"} and feats["visual_tags"] == ["red_bike", "helmet"]
    assert json.loads(row["sections"]) == [{"code": "BNS 304"}]  # jsonb passes through as a JSON string


def test_q_case_empty_lists_are_brackets_not_null(sample):
    (row,) = sample.named("q_case", agent="Planner", crime_id="CHN-A-2").dicts()
    for key in ("vehicles", "statements", "evidence", "forensics"):
        assert row[key] == "[]", key
    assert row["features"] is None


def test_q_case_unknown_id_returns_nothing(sample):
    assert sample.named("q_case", agent="Planner", crime_id="NOPE").rows == []


def test_q_features_for_a_list_of_ids(sample):
    rows = sample.named("q_features", agent="Linker", ids="CHN-A-1,CHN-A-2,NOPE").dicts()
    assert [r["crime_id"] for r in rows] == ["CHN-A-1"]  # A-2 has no features row
    r = rows[0]
    assert json.loads(r["visual_tags"]) == ["red_bike", "helmet"] and json.loads(r["mo"]) == {"entry": "snatch"}
    assert r["reviewed_by_officer"] is False and r["model"] == "nvidia/nemotron"


@pytest.mark.skipif(not (GENERATED / "supabase" / "crimes.jsonl").exists(), reason="nexus-1 generated data not local")
def test_twins_on_the_generated_city(tmp_path):
    """Local check on nexus-1's full generated data (jsonl -> parquet, as the sample bundle will be)."""
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    con = duckdb.connect()
    for t in ("crimes", "crime_vehicles", "statements"):
        src = (GENERATED / "supabase" / f"{t}.jsonl").as_posix()
        con.execute(f"COPY (SELECT * FROM read_json_auto('{src}')) TO '{(d / 'sb' / f'{t}.parquet').as_posix()}'"
                    " (FORMAT PARQUET)")
    for t in ("evidence_media", "forensics", "crime_features"):  # not generated yet: empty with the contract shape
        con.execute(f"COPY ({TABLES[t]} LIMIT 0) TO '{(d / 'sb' / f'{t}.parquet').as_posix()}' (FORMAT PARQUET)")
    c = _client(d, tmp_path)
    cid = con.execute(f"SELECT crime_id FROM '{(d / 'sb' / 'crime_vehicles.parquet').as_posix()}' "
                      "WHERE plate_pattern IS NOT NULL LIMIT 1").fetchone()[0]
    (row,) = c.named("q_case", agent="Planner", crime_id=cid).dicts()
    assert row["crime_id"] == cid and json.loads(row["vehicles"]) and row["evidence"] == "[]"


CAND = """SELECT * FROM (VALUES
 ('A', 'PS-1', 'robbery', NULL, '2026-10-14T19:40:00+05:30', 13.0000, 80.2500, 'h', 'g'),
 ('B', 'PS-1', 'robbery', NULL, '2026-09-20T10:00:00+05:30', 13.0010, 80.2500, 'h', 'g'),  -- 0.111 km, 24 d
 ('C', 'PS-2', 'robbery', NULL, '2026-10-15T01:00:00+05:30', 13.0100, 80.2500, 'h', 'g'),  -- 1.112 km, 1 UTC day
 ('D', 'PS-2', 'robbery', NULL, '2026-08-01T10:00:00+05:30', 13.0010, 80.2500, 'h', 'g'),  -- 74 d: too old
 ('E', 'PS-2', 'theft',   NULL, '2026-10-14T19:00:00+05:30', 13.0010, 80.2500, 'h', 'g'),  -- other category
 ('F', 'PS-3', 'robbery', NULL, '2026-10-10T10:00:00+05:30', 13.1000, 80.2500, 'h', 'g')   -- 11.1 km: too far
) t(crime_id, station_id, category, sub_type, occurred_from, lat, lon, h3_r9, geohash7)"""


def test_q_candidates_filters_orders_and_formats(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    duckdb.connect().execute(f"COPY ({CAND}) TO '{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    rows = _client(d, tmp_path).named("q_candidates", agent="Linker", crime_id="A", days=45, ring=6).dicts()
    assert [r["crime_id"] for r in rows] == ["B", "C"]
    b, c = rows
    assert b["km_apart"] == 0.111 and b["days_apart"] == 24 and b["same_station"] is True
    assert c["km_apart"] == 1.112 and c["same_station"] is False
    # A is 14:10 UTC on the 14th, C is 19:30 UTC on the 14th: same UTC date, so 0 whole days (Spark datediff).
    assert c["days_apart"] == 0
    assert b["occurred_from"] == "2026-09-20T10:00:00+05:30"   # ISO string in city time
    assert _client(d, tmp_path).named("q_candidates", agent="Linker", crime_id="A", days=45, ring=0.5).dicts()[0][
        "crime_id"] == "B"


@pytest.mark.skipif(not (GENERATED / "supabase" / "crimes.jsonl").exists(), reason="nexus-1 generated data not local")
def test_q_candidates_hero_on_the_generated_city(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    src = (GENERATED / "supabase" / "crimes.jsonl").as_posix()
    duckdb.connect().execute(f"COPY (SELECT * FROM read_json_auto('{src}')) TO "
                             f"'{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    rows = _client(d, tmp_path).named("q_candidates", agent="Linker", crime_id="CHN-AD-2026-001182",
                                      days=45, ring=6, limit=5000).dicts()
    first = rows[0]
    assert (first["crime_id"], first["km_apart"], first["days_apart"]) == ("CHN-AD-2026-001078", 0.162, 24)
    assert all(r["km_apart"] <= 6 and r["days_apart"] <= 45 for r in rows)
