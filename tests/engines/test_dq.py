"""WS1-14 data-quality views: q_dq_flags (DuckDB twin run for real) and zetaris/20_dq.sql (generated, same rules)."""

import math
from pathlib import Path

import duckdb
import pytest

from app.adapters import dq_rules
from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient
from app.config import Settings, load_city
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]

# sha256 of zetaris/20_dq.sql and 40_feeds.sql on main before the {{src:...}} placeholders (WS1-19): rendered
# for supabase, the files must stay byte-identical to what is registered live today.
SUPABASE_SHA = {"20_dq.sql": "d4d64a3bbac4aa575b3f3c7dd82f0afcd1543d65f2a8fccc964d3cd2a68a36b5",
                "40_feeds.sql": "c67eb214df729ae66cd1b5c505471286a9355a34b2e69019dd877545fc40dc74"}


def rendered(text: str, data: str = "supabase") -> str:
    """Fill {{src:...}} the way register.py does, from the one source map."""
    from app.adapters.zetaris_sources import sources

    for key, value in sources(data).items():
        text = text.replace("{{src:%s}}" % key, value)
    return text

ROWS = [
    # crime_id, source, station, category, occurred_from, occurred_to, reported_at, lat, lon, h3_r9, sections_raw
    ("C1", "sb.crimes", "PS-A", "chain_snatching", "2026-10-01 19:00", "2026-10-01 19:10", "2026-10-01 21:00",
     13.00, 80.25, "89a", None),
    ("C2", "sb.crimes", "PS-B", "chain_snatching", "2026-10-01 19:20", None, "2026-10-02 09:00",
     13.001, 80.2505, "89x", None),     # duplicate of C1 at another station, geocoded into a neighbouring cell
    ("C3", "sb.crimes", "PS-A", "chain_snatching", "2026-10-03 19:00", None, "2026-10-03 20:00",
     13.00, 80.25, "89a", None),                                             # same cell, 2 days later: clean
    ("C4", "s3csv.cctns", "PS-A", "theft", "2026-10-04 10:00", None, "2026-10-04 09:00",
     12.50, 80.25, "89b", "IPC 379 r/w 34"),                                 # bad geo + time + unmapped
    ("C5", "sb.crimes", "PS-C", "theft", "2026-10-05 10:00", None, "2026-10-05 11:00",
     None, None, None, None),                                                # no coordinates
    ("C6", "s3pq.archive", "PS-A", "theft", "2026-10-06 10:00", "2026-10-06 09:00", "2026-10-06 12:00",
     13.05, 80.20, "89c", None),                                             # ends before it starts
]


@pytest.fixture
def client(tmp_path):
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False))
    c._duck = duckdb.connect(":memory:")
    c._duck.execute("CREATE TABLE v_crime_unified (crime_id VARCHAR, source VARCHAR, station_id VARCHAR, "
                    "category VARCHAR, occurred_from TIMESTAMP, occurred_to TIMESTAMP, reported_at TIMESTAMP, "
                    "lat DOUBLE, lon DOUBLE, h3_r9 VARCHAR, sections_raw VARCHAR)")
    c._duck.executemany("INSERT INTO v_crime_unified VALUES (?,?,?,?,?,?,?,?,?,?,?)", ROWS)
    return c


def _flags(client, ids):
    res = client.named("q_dq_flags", agent="Planner", ids=",".join(ids))
    assert res.source == "sample" and res.columns == dq_rules.COLUMNS
    return sorted((r["crime_id"], r["rule"], r["other_id"]) for r in res.dicts())


def test_each_planted_defect_is_flagged_and_clean_rows_are_not(client):
    got = _flags(client, ["C1", "C2", "C3", "C4", "C5", "C6"])
    assert got == [
        ("C1", "duplicate_fir", "C2"), ("C2", "duplicate_fir", "C1"),
        ("C4", "bad_geo", None), ("C4", "time_inconsistent", None), ("C4", "unmapped_section", None),
        ("C5", "bad_geo", None),
        ("C6", "time_inconsistent", None),
    ]


def test_only_requested_ids_are_returned(client):
    assert _flags(client, ["C3"]) == []
    assert {r[0] for r in _flags(client, ["C2", "C5"])} == {"C2", "C5"}


def test_details_are_written_in_code(client):
    rows = client.named("q_dq_flags", agent="Planner", ids="C1,C4").dicts()
    dup = next(r for r in rows if r["rule"] == "duplicate_fir")
    assert dup["detail"] == "same chain_snatching within 20 min and 111 m, filed at PS-B via sb.crimes"
    geo = next(r for r in rows if r["rule"] == "bad_geo")
    assert geo["detail"].startswith("outside city bounds: 12.5")


def test_bounds_come_from_the_city_pack_not_code():
    bounds = dq_rules.city_bounds(load_city("chennai"))
    sample = NAMED_QUERIES["q_dq_flags"].sample
    assert f"lon < {bounds['west']}" in sample and f"lat > {bounds['north']}" in sample
    code = (ROOT / "services/api/app/adapters/dq_rules.py").read_text(encoding="utf-8")
    assert str(bounds["west"]) not in code and str(bounds["north"]) not in code


def test_zetaris_file_is_generated_from_the_same_rules():
    raw = (ROOT / "zetaris" / "20_dq.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert raw == dq_rules.dq_file(), "regenerate: cd services/api && python -m app.adapters.dq_rules"
    committed = rendered(raw)
    for view in ("dq_duplicate_firs", "dq_bad_geo", "dq_time_inconsistent", "dq_unmapped_sections", "dq_flags",
                 "dq_orphan_evidence", "dq_tip_without_incident", "dq_stale_cameras", "dq_impossible_travel"):
        assert f"CREATE OR REPLACE SCHEMASTORE VIEW {view} WITH CONTAINER nexus AS" in committed
    assert "{{city:map.bounds.0}}" in committed and "80.05" not in committed
    # Same rule text in both dialects, modulo the dialect substitutions.
    spark = dq_rules.rule_sql("time_inconsistent", dq_rules.SPARK, dq_rules.BOUND_PLACEHOLDERS)
    duck = dq_rules.rule_sql("time_inconsistent", dq_rules.DUCK, dq_rules.BOUND_PLACEHOLDERS)
    live_view = dq_rules.SPARK_VIEW.replace("STRING", "VARCHAR")
    assert spark.replace("STRING", "VARCHAR").replace(live_view, "v_crime_unified") == duck
    # Creates the container itself (repeats are skipped) and reads the unified crime view.
    assert committed.index("CREATE SCHEMASTORE CONTAINER nexus;") < committed.index("SCHEMASTORE VIEW")
    sql_only = "\n".join(line for line in committed.splitlines() if not line.startswith("--"))
    assert "FROM nexus.v_crime_unified" in sql_only


def test_live_views_are_sorted_and_dq_flags_reads_the_rule_views():
    # D-031: without a sort Zetaris applies the REST limit / count(*) before filters it cannot push down.
    views = [s for s in rendered(dq_rules.dq_file()).split(";\n") if "SCHEMASTORE VIEW" in s]
    assert len(views) == 9 and all("\nORDER BY " in v for v in views)
    flags = next(v for v in views if "VIEW dq_flags " in v)
    # Zetaris rejects a query that references one schema-store view twice; the rule views are four different views.
    assert "v_crime_unified" not in flags
    for name in ("dq_duplicate_firs", "dq_bad_geo", "dq_time_inconsistent", "dq_unmapped_sections"):
        assert f"FROM nexus.{name}" in flags
    assert NAMED_QUERIES["q_dq_flags"].lightning.endswith("ORDER BY crime_id, rule, other_id")  # snapshot (0007_14)
    assert NAMED_QUERIES["q_dq_flags"].lightning_files.endswith("ORDER BY crime_id, rule")


@pytest.mark.parametrize("name", ["20_dq.sql", "40_feeds.sql"])
def test_register_py_fills_every_placeholder_from_the_city_pack(name):
    """The files must render through register.py itself (its dry-run path), with no placeholder left over."""
    import importlib.util

    import yaml

    spec = importlib.util.spec_from_file_location("register", ROOT / "zetaris" / "register.py")
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    city = yaml.safe_load((ROOT / "cities" / "chennai" / "city.yaml").read_text(encoding="utf-8"))
    stmts = reg.statements((ROOT / "zetaris" / name).read_text(encoding="utf-8"))
    shown = [reg.fill(stmt, city, "2026-09-26", "2026-10-26")[1] for stmt in stmts]
    assert shown and not any("{{" in s for s in shown)
    if name == "20_dq.sql":
        assert any(f"lon < {dq_rules.city_bounds(city)['west']}" in s for s in shown)


def test_dq_reads_only_registered_tip_columns():
    sql = rendered((ROOT / "zetaris" / "20_dq.sql").read_text(encoding="utf-8"))
    assert "sb.tips_v" in sql and "sb.tips " not in sql


@pytest.mark.parametrize("name", ["20_dq.sql", "40_feeds.sql"])
def test_supabase_rendering_is_byte_identical_to_the_registered_files(name):
    import hashlib

    text = (ROOT / "zetaris" / name).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(rendered(text).encode("utf-8")).hexdigest() == SUPABASE_SHA[name]


@pytest.mark.parametrize("name", ["20_dq.sql", "40_feeds.sql"])
def test_files_rendering_reads_only_the_file_store_and_its_own_container(name):
    import re

    text = (ROOT / "zetaris" / name).read_text(encoding="utf-8")
    code = "\n".join(line for line in rendered(text, "files").splitlines() if not line.lstrip().startswith("--"))
    assert "{{src:" not in code
    assert not re.search(r"\b(sb|nexus)\.", code)  # never the live datasource or the live container
    assert not re.search(r"CONTAINER nexus\b", code)
    assert "CREATE SCHEMASTORE CONTAINER nexusfs;" in code and "nexusfs.v_crime_unified" in code
    if name == "20_dq.sql":
        assert "nexus_fs.crimes" in code and "nexus_fs.evidence_media" in code and "nexus_fs.tips_v" in code
    else:
        assert "nexus_feeds.rest_news" in code  # the REST feed tables are shared by both modes


def _haversine_km(lat1, lon1, lat2, lon2):
    """Same R = 6371 expression as the SQL, so the test checks the query rather than a second formula."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def test_impossible_travel_view_matches_its_duckdb_twin_and_standalone_select():
    spark = dq_rules.impossible_travel_sql(sample=False)
    duck = dq_rules.impossible_travel_sql(sample=True)
    assert spark.replace("unix_timestamp", "epoch").replace("s3pq.anpr_reads", "anpr_reads").replace(
        "s3csv.anpr_cameras", "anpr_cameras") == duck
    assert "LAG(camera_id) OVER (PARTITION BY plate_text ORDER BY read_at)" in spark
    assert "CAST(c.lat AS DOUBLE)" in spark and "CAST(c.lon AS DOUBLE)" in spark
    assert f"WHERE implied_kmh > {dq_rules.IMPOSSIBLE_KMH}" in spark
    raw = (ROOT / "zetaris" / "20_dq.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert f"SCHEMASTORE VIEW dq_impossible_travel WITH CONTAINER {{{{src:nexus}}}} AS\n{spark}\n" in raw
    assert raw.rstrip().endswith(f"ORDER BY {dq_rules.TRAVEL_ORDER};")
    # The other rule views are untouched: dq_flags still unions only the four crime-level checks.
    flags = next(s for s in raw.split("CREATE OR REPLACE SCHEMASTORE VIEW ") if s.startswith("dq_flags "))
    assert "dq_impossible_travel" not in flags and "anpr_reads" not in flags
    standalone = (ROOT / "impossible_travel.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert standalone == dq_rules.impossible_travel_file()
    body = "\n".join(line for line in standalone.splitlines() if line.strip() and not line.startswith("--"))
    assert body == f"{spark}\nORDER BY {dq_rules.TRAVEL_ORDER}"
    assert "s3pq.anpr_reads" in body and "s3csv.anpr_cameras" in body


def test_impossible_travel_flags_only_pairs_over_150_kmh():
    # C1 and C2 are 1 degree of latitude apart: 6371 * pi/180 km, about 111.2 km.
    # 30 min → ~222 km/h (flag). 40 min → ~167 km/h (flag). 45 min → ~148 km/h (not).
    # Cameras are strings, as the CSV source is. Reads of one plate are inserted out of time order.
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE anpr_reads (plate_text VARCHAR, camera_id VARCHAR, read_at TIMESTAMP)")
    con.execute("CREATE TABLE anpr_cameras (camera_id VARCHAR, lat VARCHAR, lon VARCHAR)")
    con.executemany("INSERT INTO anpr_cameras VALUES (?, ?, ?)", [
        ("C1", "13.0", "80.0"), ("C2", "14.0", "80.0"), ("C3", "13.01", "80.01"),
    ])
    con.executemany("INSERT INTO anpr_reads VALUES (?, ?, ?)", [
        ("BACK", "C1", "2026-10-01 08:30:00"),   # later read inserted first
        ("BACK", "C2", "2026-10-01 08:00:00"),   # 111 km in 30 min → ~222 km/h
        ("FAST", "C2", "2026-10-01 10:40:00"),
        ("FAST", "C1", "2026-10-01 10:00:00"),   # 111 km in 40 min → ~167 km/h
        ("FAST", "C1", "2026-10-01 14:40:00"),   # back again in 4 h → ~28 km/h, not a second flag
        ("SLOW", "C1", "2026-10-01 12:00:00"),
        ("SLOW", "C2", "2026-10-01 12:45:00"),   # 111 km in 45 min → ~148 km/h
        ("NEAR", "C1", "2026-10-01 15:00:00"),
        ("NEAR", "C3", "2026-10-01 15:10:00"),
        ("SAME", "C1", "2026-10-01 16:00:00"),
        ("SAME", "C1", "2026-10-01 16:05:00"),
        ("ONCE", "C2", "2026-10-01 17:00:00"),
        ("GAP", "C1", "2026-10-01 18:00:00"),
        ("GAP", "MISSING", "2026-10-01 18:10:00"),  # unresolved camera stays in the sequence
        ("GAP", "C2", "2026-10-01 18:20:00"),       # so C1 and C2 are not one hop
        (None, "C1", "2026-10-01 19:00:00"),
        (None, "C2", "2026-10-01 19:10:00"),
    ])
    sql = f"{dq_rules.impossible_travel_sql(sample=True)}\nORDER BY {dq_rules.TRAVEL_ORDER}"
    cur = con.execute(sql)
    assert [d[0] for d in cur.description] == list(dq_rules.TRAVEL_COLUMNS)
    rows = cur.fetchall()
    assert [(r[0], r[1], r[2]) for r in rows] == [("BACK", "C2", "C1"), ("FAST", "C1", "C2")]
    km = _haversine_km(13.0, 80.0, 14.0, 80.0)
    by_plate = {r[0]: r for r in rows}
    assert by_plate["BACK"][5] == pytest.approx(km, rel=1e-9)
    assert by_plate["BACK"][6] == pytest.approx(km * 3600 / 1800, rel=1e-9)
    assert by_plate["FAST"][5] == pytest.approx(km, rel=1e-9)
    assert by_plate["FAST"][6] == pytest.approx(km * 3600 / 2400, rel=1e-9)
    assert str(by_plate["FAST"][3]).startswith("2026-10-01 10:00:00")
    assert str(by_plate["FAST"][4]).startswith("2026-10-01 10:40:00")
    assert by_plate["BACK"][6] > 150 and by_plate["FAST"][6] > 150
