"""Reference data (WS1-07): shape, ids other lanes rely on, licences, no duplicates."""

import csv
import json
from datetime import date
from pathlib import Path

import duckdb
import pytest
import yaml

from data.geo import cells, geohash

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "cities" / "chennai"
CITY = yaml.safe_load((PACK / "city.yaml").read_text(encoding="utf-8"))
W, S, E, N = CITY["map"]["bounds"]


def fc(name):
    return json.loads((PACK / name).read_text(encoding="utf-8"))["features"]


def test_geohash_known_value():
    assert geohash(57.64911, 10.40744, 11) == "u4pruydqqvj"
    c = cells(13.0012, 80.2565)
    assert len(c["geohash7"]) == 7 and c["h3_r9"] != c["h3_r8"]


def test_stations():
    st = fc("stations.geojson")
    ids = [f["properties"]["station_id"] for f in st]
    assert len(ids) == 70 == len(set(ids))
    # nexus-4 seeded demo officers at these two ids; they must stay stable.
    assert {"PS-ADYAR-J2", "PS-VELACHERY-J7"} <= set(ids)
    for f in st:
        p = f["properties"]
        assert W <= p["lon"] <= E and S <= p["lat"] <= N
        assert p["synthetic_jurisdiction"] is True
        assert f["geometry"]["type"] == "MultiPolygon"
        assert p["location_source"] == "approximate" or p["location_source"].startswith("osm:")
    assert len({f["properties"]["district"] for f in st}) == 12
    assert len({f["properties"]["region"] for f in st}) == 4


def test_wards():
    wards = fc("wards.geojson")
    nos = [f["properties"]["ward_no"] for f in wards]
    assert len(nos) == len(set(nos)) >= 200


def test_law_sections_unique_and_unverified():
    rows = list(csv.DictReader((PACK / "law_sections.csv").open(encoding="utf-8")))
    keys = [(r["ipc_code"], r["bns_code"]) for r in rows]
    assert len(keys) == len(set(keys))
    assert all(r["ipc_code"] or r["bns_code"] for r in rows)
    assert {"IPC 392", "IPC 379", "IPC 457", "IPC 302"} <= {r["ipc_code"] for r in rows}
    assert all(r["verified"] in ("true", "false") for r in rows)


def test_calendar_two_years():
    rows = list(csv.DictReader((PACK / "calendar.csv").open(encoding="utf-8")))
    years = {date.fromisoformat(r["date"]).year for r in rows}
    assert years == {2025, 2026}
    assert any(r["name"] == "Deepavali" and r["travel_heavy"] == "true" for r in rows)


@pytest.mark.parametrize("col", ["poi_id", "poi_type", "lat", "lon", "h3_r9", "h3_r8", "geohash7", "licence"])
def test_pois_columns(col):
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM '{(ROOT / 'data/reference/osm_pois.parquet').as_posix()}'").fetchall()]
    assert col in cols


def test_pois_inside_bounds_and_typed():
    p = (ROOT / "data/reference/osm_pois.parquet").as_posix()
    con = duckdb.connect()
    n, bad, dup = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE lon NOT BETWEEN {W} AND {E} OR lat NOT BETWEEN {S} AND {N}),"
        f" count(*) - count(DISTINCT poi_id) FROM '{p}'").fetchone()
    assert n > 5000 and bad == 0 and dup == 0
    types = {r[0] for r in con.execute(f"SELECT DISTINCT poi_type FROM '{p}'").fetchall()}
    assert {"bus_stop", "temple", "jeweller", "atm"} <= types


def test_manifest_hashes_match():
    import hashlib
    man = json.loads((ROOT / "data/reference/MANIFEST.json").read_text(encoding="utf-8"))
    for rel, h in man["sha256"].items():
        b = (ROOT / rel).read_bytes()
        if not rel.endswith(".parquet"):
            b = b.replace(b"\r\n", b"\n")
        assert hashlib.sha256(b).hexdigest() == h, rel
