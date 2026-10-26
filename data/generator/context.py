"""Everything the generator reads from the city pack, plus seeded random streams.

Determinism: every random stream is `random.Random` seeded from sha256(seed, name), never
from Python's hash() (which changes per process) or the wall clock. The run end date is
pinned in the city pack.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import yaml
from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[2]


def _tz(offset: str) -> timezone:
    sign = -1 if offset.startswith("-") else 1
    hh, mm = offset.lstrip("+-").split(":")
    return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))


@dataclass
class Station:
    station_id: str
    code: str
    name: str
    locality: str
    district: str
    region: str
    zone: str | None
    lat: float
    lon: float
    geom: object
    feature: dict


@dataclass
class Ctx:
    seed: int
    city: str
    pack: Path
    cfg: dict
    series_cfg: dict
    names: dict
    tz: timezone
    start: date
    end: date
    stations: list[Station]
    by_code: dict[str, Station]
    wards: list[tuple[int, str, object]]
    ward_features: list[dict]
    pois: dict[str, list[tuple[float, float, str | None]]]
    sections: dict[str, dict]
    section_rows: list[dict]
    festival_days: set[date]
    _streams: dict[str, random.Random] = field(default_factory=dict)

    def rng(self, name: str) -> random.Random:
        """A named, seeded stream: the same name always gives the same sequence."""
        if name not in self._streams:
            h = hashlib.sha256(f"{self.seed}:{name}".encode()).digest()
            self._streams[name] = random.Random(int.from_bytes(h[:8], "big"))
        return self._streams[name]

    # ---------- spatial ----------
    def station_at(self, lat: float, lon: float) -> Station | None:
        p = Point(lon, lat)
        for i in self._st_tree.query(p):
            if self._st_prep[i].contains(p):
                return self.stations[i]
        return None

    def ward_at(self, lat: float, lon: float) -> int | None:
        p = Point(lon, lat)
        for i in self._w_tree.query(p):
            if self._w_prep[i].contains(p):
                return self.wards[i][0]
        return None

    def local(self, d: date, hour_float: float) -> datetime:
        """Local datetime for a date and fractional hour (hours >= 24 roll into the next day)."""
        minutes = int(round(hour_float * 60))
        return datetime(d.year, d.month, d.day, tzinfo=self.tz) + timedelta(minutes=minutes)

    def days(self) -> list[date]:
        n = (self.end - self.start).days + 1
        return [self.start + timedelta(days=i) for i in range(n)]


def load(seed: int, city: str = "chennai", months: int | None = None) -> Ctx:
    pack = ROOT / "cities" / city
    gen = pack / "generator"
    cfg = yaml.safe_load((gen / "config.yaml").read_text(encoding="utf-8"))
    series_cfg = yaml.safe_load((gen / "series.yaml").read_text(encoding="utf-8"))
    names = yaml.safe_load((gen / "names.yaml").read_text(encoding="utf-8"))
    tz = _tz(cfg["utc_offset"])
    end = date.fromisoformat(cfg["end_date"])
    m = months or cfg["months"]
    start = end - timedelta(days=round(m * 30.44))  # m months back, to the day

    st_fc = json.loads((pack / "stations.geojson").read_text(encoding="utf-8"))["features"]
    stations = []
    for f in sorted(st_fc, key=lambda f: f["properties"]["station_id"]):
        p = f["properties"]
        stations.append(Station(
            station_id=p["station_id"], code=p["code"], name=p["name"], locality=p["name"].split(" (")[0],
            district=p["district"], region=p["region"], zone=p.get("zone"), lat=p["lat"], lon=p["lon"],
            geom=shape(f["geometry"]), feature=f))
    w_fc = json.loads((pack / "wards.geojson").read_text(encoding="utf-8"))["features"]
    wards = [(f["properties"]["ward_no"], f["properties"]["zone"], shape(f["geometry"]))
             for f in sorted(w_fc, key=lambda f: f["properties"]["ward_no"])]

    con = duckdb.connect()
    con.execute("SET threads=1")
    rows = con.execute(
        f"SELECT poi_type, lat, lon, name FROM '{(ROOT / 'data/reference/osm_pois.parquet').as_posix()}' "
        "ORDER BY poi_id").fetchall()
    con.close()
    pois: dict[str, list] = {}
    for t, lat, lon, name in rows:
        pois.setdefault(t, []).append((lat, lon, name))

    section_rows = list(csv.DictReader((pack / "law_sections.csv").open(encoding="utf-8")))
    sections = {r["bns_code"]: r for r in section_rows if r["bns_code"]}
    festival = set()
    for r in csv.DictReader((pack / "calendar.csv").open(encoding="utf-8")):
        if r["travel_heavy"] == "true":
            d = date.fromisoformat(r["date"])
            festival.update(d + timedelta(days=k) for k in range(-3, 4))

    ctx = Ctx(seed=seed, city=city, pack=pack, cfg=cfg, series_cfg=series_cfg, names=names, tz=tz,
              start=start, end=end, stations=stations, by_code={s.code: s for s in stations},
              wards=wards, ward_features=w_fc, pois=pois, sections=sections, section_rows=section_rows,
              festival_days=festival)
    ctx._st_tree = STRtree([s.geom for s in stations])
    ctx._st_prep = [prep(s.geom) for s in stations]
    ctx._w_tree = STRtree([w[2] for w in wards])
    ctx._w_prep = [prep(w[2]) for w in wards]
    return ctx
