"""data/fs_export.py: the nexus_fs file-store tables have the sb shapes (WS1-19)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

from app.adapters.zetaris_sources import FILE_TABLES
from data import fs_export
from data.fixtures.export import FEATURES_COLUMNS, TIPS_COLUMNS
from zetaris import stage_files

ROOT = Path(__file__).resolve().parents[2]
CID = "CHN-AD-2026-001182"


def _jl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _gen(tmp: Path) -> tuple[Path, Path]:
    sb = tmp / "gen" / "supabase"
    sb.mkdir(parents=True)
    _jl(sb / "crimes.jsonl", [{
        "crime_id": CID, "source": "sb.crimes", "source_row_id": "x", "station_id": "PS-ADYAR-J2", "fir_no": "1182/2026",
        "category": "chain_snatching", "sub_type": "chain_snatching", "sections": [{"code": "BNS 304(2)", "ipc_equiv": None}],
        "occurred_from": "2026-10-14T19:40:00+05:30", "occurred_to": "2026-10-14T19:45:00.250000+05:30",
        "reported_at": "2026-10-14T21:00:00+05:30", "lat": 13.0012, "lon": 80.2565, "address": "LB Road", "ward_no": 173,
        "h3_r9": "a", "h3_r8": "b", "geohash7": "c", "week": "2026-W42", "severity": 3,
        "property": [{"type": "gold_chain", "weight_g": 24, "value_inr": 152000}], "weapon": None,
        "offenders_described": [], "victims": [], "status": "open", "narrative": "n", "synthetic": True}])
    _jl(sb / "statements.jsonl", [{"statement_id": "ST-1", "crime_id": CID, "witness_ref": "W-1", "mode": "text",
                                   "text": "red bike", "audio_path": None, "transcript_model": None,
                                   "recorded_at": "2026-10-16T08:11:11Z", "source": "s", "source_row_id": "y",
                                   "synthetic": True}])
    _jl(sb / "crime_vehicles.jsonl", [
        {"crime_id": CID, "role": "used_by_offender", "vehicle_type": "motorcycle", "plate_pattern": None,
         "make_model": None, "colour": "red", "synthetic": True},
        {"crime_id": CID, "role": "used_by_offender", "vehicle_type": "motorcycle", "plate_pattern": "TN09??4471",
         "make_model": "Bajaj Pulsar 150", "colour": "red", "synthetic": True}])
    for f in ("evidence_media", "section_map", "stations"):
        _jl(sb / f"{f}.jsonl", [])
    _jl(sb / "tips.jsonl", [{"tip_id": "TIP-1", "public_incident_id": None, "channel": "web", "category": "c",
                             "text": "SECRET TEXT", "tip_code_hash": "HASH", "follow_up_enabled": True, "guard": None,
                             "approx_cell": "z", "received_week": "2026-W43", "status": "new", "source": "sb.tips",
                             "source_row_id": "TIP-1", "synthetic": True}])
    fx = tmp / "fixtures"
    fx.mkdir()
    con = duckdb.connect()
    for name, cols, row in (
        ("crime_features_v", FEATURES_COLUMNS,
         (CID, "mo-v4", '{"target": "woman"}', '["red_motorcycle"]', '{}', "m", "r", 0.85, False, True, '{"mo" : {}}')),
        ("tip_verdicts", TIPS_COLUMNS, ("TIP-1", '{"verdict": "clean"}', "screened")),
    ):
        con.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t in cols)})")
        con.execute(f"INSERT INTO {name} VALUES ({', '.join('?' for _ in cols)})", row)
        con.execute(f"COPY {name} TO '{(fx / f'{name}.parquet').as_posix()}' (FORMAT PARQUET)")
    return tmp / "gen", fx


def _read(out: Path, table: str) -> tuple[list[tuple[str, str]], list[dict]]:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    p = (out / table / "part-0.parquet").as_posix()
    cols = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM '{p}'").fetchall()]
    r = con.execute(f"SELECT * FROM '{p}'")
    names = [d[0] for d in r.description]
    return cols, [dict(zip(names, row)) for row in r.fetchall()]


def test_every_table_has_the_sb_columns_and_types(tmp_path):
    gen, fx = _gen(tmp_path)
    counts = fs_export.build(gen, tmp_path / "fs", fx)
    assert set(counts) == set(FILE_TABLES)
    for table, schema in fs_export.SCHEMAS.items():
        cols, _ = _read(tmp_path / "fs", table)
        want = [(c, "TIMESTAMP WITH TIME ZONE" if t == "TIMESTAMPTZ" else t) for c, t in schema]
        assert cols == want, table


def test_text_forms_match_postgres(tmp_path):
    gen, fx = _gen(tmp_path)
    fs_export.build(gen, tmp_path / "fs", fx)
    _, (crime,) = _read(tmp_path / "fs", "crimes")
    assert crime["sections"] == '[{"code": "BNS 304(2)", "ipc_equiv": null}]'  # jsonb: length, then bytes
    assert crime["property"] == '[{"type": "gold_chain", "weight_g": 24, "value_inr": 152000}]'
    _, (b,) = _read(tmp_path / "fs", "case_bundle_v")
    assert b["occurred_from"] == "2026-10-14T19:40:00+05:30"
    assert b["occurred_to"] == "2026-10-14T19:45:00.25+05:30"
    # json_build_object uses ' : '; Postgres sorts the NULL plate last.
    assert b["vehicles"].startswith('[{"role" : "used_by_offender", "type" : "motorcycle", "plate" : "TN09??4471"')
    assert '"plate" : null' in b["vehicles"].split("}, {")[1]
    assert b["statements"] == ('[{"statement_id" : "ST-1", "witness_ref" : "W-1", "mode" : "text", '
                               '"text" : "red bike", "recorded_at" : "2026-10-16T13:41:11+05:30"}]')
    assert b["evidence"] == "[]" and b["forensics"] == "[]" and b["features"] == '{"mo" : {}}'


def test_tips_keep_only_tips_v_columns_and_the_recorded_verdict(tmp_path):
    gen, fx = _gen(tmp_path)
    fs_export.build(gen, tmp_path / "fs", fx)
    cols, (tip,) = _read(tmp_path / "fs", "tips_v")
    names = [c for c, _ in cols]
    assert "text" not in names and "tip_code_hash" not in names
    assert "SECRET" not in json.dumps(tip, default=str) and "HASH" not in json.dumps(tip, default=str)
    assert tip["status"] == "screened" and tip["guard"] == '{"verdict": "clean"}'


def test_registration_staging_and_export_name_the_same_tables():
    assert tuple(stage_files.FS_TABLES) == FILE_TABLES
    sql = (ROOT / "zetaris" / "02_fs.sql").read_text(encoding="utf-8")
    assert re.findall(r"FILESTORE TABLE (\w+) FROM nexus_fs", sql) == list(FILE_TABLES)
    for t in FILE_TABLES:
        assert f'path "file:///home/zetaris/customer-data/shared/nexus/fs/{t}/"' in sql


def test_jsonb_key_order_is_length_then_bytes():
    assert fs_export.jsonb_text({"verbal": None, "target": "w", "escape": "x", "approach": "y", "violence": "z"}) == \
        '{"escape": "x", "target": "w", "verbal": null, "approach": "y", "violence": "z"}'
