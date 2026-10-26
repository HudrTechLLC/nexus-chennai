"""q_context (spec E5 v_context): calendar, nearby POI types and hourly weather for one crime."""

from pathlib import Path

import duckdb
import pytest

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient, render
from app.adapters.zetaris_queries_n2 import CONTEXT_COLUMNS
from app.config import Settings
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]

CRIMES = """SELECT * FROM (VALUES
 ('C1', '2026-10-20T21:15:00+05:30', 13.0000, 80.2500),
 ('C2', '2026-10-25T00:30:00+05:30', 13.2000, 80.1000)
) t(crime_id, occurred_from, lat, lon)"""
POIS = """SELECT * FROM (VALUES
 ('P1', 'bus_stop', 13.0010, 80.2500),
 ('P2', 'atm',      13.0030, 80.2500),
 ('P3', 'atm',      13.0000, 80.2520),
 ('P4', 'temple',   13.0100, 80.2500)
) t(poi_id, poi_type, lat, lon)"""
CALENDAR = ("date,name,kind,travel_heavy,verified\n2026-10-20,Deepavali,festival,true,false\n"
            "2026-10-20,Bank holiday,public_holiday,false,false\n")


@pytest.fixture
def client(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    (d / "ref").mkdir()
    con = duckdb.connect()
    con.execute(f"COPY ({CRIMES}) TO '{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY ({POIS}) TO '{(d / 'ref' / 'osm_pois.parquet').as_posix()}' (FORMAT PARQUET)")
    (d / "ref" / "calendar.csv").write_text(CALENDAR, encoding="utf-8")
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False))
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{d.as_posix()}'")
    return c


def _ctx(client, cid):
    res = client.named("q_context", agent="Planner", crime_id=cid)
    assert res.columns == CONTEXT_COLUMNS
    return res.dicts()


def test_context_for_a_crime_on_a_festival_evening(client):
    (r,) = _ctx(client, "C1")
    assert (r["local_date"], r["hour_of_day"], r["day_type"]) == ("2026-10-20", 21, "weekday")
    assert r["holidays"] == "Bank holiday; Deepavali" and r["holiday_kinds"] == "festival,public_holiday"
    assert r["travel_heavy"] is True
    assert r["poi_types"] == "atm,bus_stop" and r["pois_within"] == 3        # the temple is 1.1 km away
    assert r["nearest_poi_type"] == "bus_stop" and r["nearest_poi_km"] == 0.111
    assert r["temperature_c"] is None and r["weather_code"] is None          # no weather in the sample bundle


def test_local_date_and_weekend_use_city_time(client):
    (r,) = _ctx(client, "C2")   # 00:30 IST on Sunday 25 Oct = Saturday 24 Oct in UTC
    assert (r["local_date"], r["hour_of_day"], r["day_type"]) == ("2026-10-25", 0, "weekend")
    assert r["holidays"] is None and r["travel_heavy"] is False and r["pois_within"] == 0


def test_unknown_crime_returns_nothing(client):
    assert _ctx(client, "NOPE") == []


def test_lightning_uses_registered_names_and_the_weather_view():
    sql = render(NAMED_QUERIES["q_context"].lightning, {"crime_id": "C1"})
    for name in ("sb.crimes", "s3pq.osm_pois", "s3csv.calendar", "nexus.weather_hourly", "poi_type", "min_by"):
        assert name in sql
    feeds = (ROOT / "zetaris" / "40_feeds.sql").read_text(encoding="utf-8")
    assert "CREATE LIGHTNING REST TABLE rest_weather" in feeds and "VIEW weather_hourly" in feeds
    assert "{{city:map.center.1}}" in feeds and "timezone=auto" in feeds
