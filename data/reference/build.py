"""Build a city pack's reference files from data/reference/raw/ (run fetch.py first).

    python -m data.reference.build [--city chennai]

Writes (deterministic; same raw input -> byte-identical output):
  cities/<city>/wards.geojson     wards (merged by ward number), with zone
  cities/<city>/stations.geojson  stations: seed list snapped to OSM police nodes where one is
                                  near and named alike; jurisdiction = Voronoi cell (synthetic)
  data/reference/osm_pois.parquet POIs with normalised type and precomputed cells
  data/reference/MANIFEST.json    row counts and sha256 of every output
Nothing city-specific is in this file; it all comes from the city pack (D-004).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

import duckdb
import yaml
from shapely import voronoi_polygons
from shapely.geometry import MultiPoint, MultiPolygon, Point, box, mapping, shape
from shapely.ops import unary_union

from data.geo import cells

ROOT = Path(__file__).resolve().parents[2]
REF = Path(__file__).resolve().parent
RAW = REF / "raw"
COORD_DP = 6


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _round_geom(geom):
    """Round coordinates so output is stable across platforms."""
    return json.loads(json.dumps(mapping(geom)), parse_float=lambda s: round(float(s), COORD_DP))


def _multi(geom) -> MultiPolygon:
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
    return MultiPolygon(polys)


def write_geojson(path: Path, features: list[dict]) -> None:
    fc = {"type": "FeatureCollection", "features": features}
    text = json.dumps(fc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))  # LF on every OS, so hashes match the git checkout


# ---------- wards ----------
def build_wards(pack: Path, src: dict) -> tuple[list[dict], dict[int, object]]:
    raw = json.loads((RAW / "wards.geojson").read_text(encoding="utf-8"))
    by_no: dict[int, list] = {}
    zone: dict[int, str] = {}
    for f in raw["features"]:
        p = f["properties"]
        no = int(p[src["number_property"]])
        by_no.setdefault(no, []).append(shape(f["geometry"]).buffer(0))
        zone[no] = str(p.get(src["zone_property"]) or "").title()
    feats, geoms = [], {}
    for no in sorted(by_no):
        g = _multi(unary_union(by_no[no]).simplify(0.00005, preserve_topology=True))
        geoms[no] = g
        c = g.representative_point()
        feats.append({
            "type": "Feature",
            "properties": {"ward_no": no, "name": f"Ward {no}", "zone": zone[no],
                           "label_lat": round(c.y, COORD_DP), "label_lon": round(c.x, COORD_DP)},
            "geometry": _round_geom(g),
        })
    write_geojson(pack / "wards.geojson", feats)
    return feats, geoms


# ---------- stations ----------
def _osm_points(path: Path) -> list[dict]:
    els = json.loads(path.read_text(encoding="utf-8"))["elements"]
    out = []
    for e in els:
        t = e.get("tags", {})
        name = " ".join(filter(None, [t.get("name"), t.get("name:en")]))
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        if name and lat is not None:
            out.append({"osm": f"{e['type']}/{e['id']}", "name": name, "lat": lat, "lon": lon})
    return sorted(out, key=lambda r: r["osm"])


def station_id(fmt: str, name: str, code: str) -> str:
    return fmt.format(name=re.sub(r"[^A-Z0-9]", "", name.upper()), code=code)


def build_stations(pack: Path, ward_feats: list[dict], ward_geoms: dict, city: dict) -> list[dict]:
    police = yaml.safe_load((pack / "police.yaml").read_text(encoding="utf-8"))
    osm = _osm_points(RAW / "osm_police.json")
    seeds = list(csv.DictReader((pack / "stations_seed.csv").open(encoding="utf-8")))
    rows = []
    for s in seeds:
        alat, alon = float(s["approx_lat"]), float(s["approx_lon"])
        token = s["match"].lower()
        near = [o for o in osm if token in o["name"].lower()
                and km(alat, alon, o["lat"], o["lon"]) <= police["osm_match_radius_km"]]
        best = min(near, key=lambda o: km(alat, alon, o["lat"], o["lon"])) if near else None
        lat, lon = (best["lat"], best["lon"]) if best else (alat, alon)
        district = police["districts"][re.match(r"[A-Z]+", s["code"]).group(0)]
        rows.append({
            "station_id": station_id(police["id_format"], s["name"], s["code"]),
            "code": s["code"], "name": f"{s['name']} ({s['code']})", "type": police["station_type"],
            "district": district, "region": police["regions"][district],
            "lat": round(lat, COORD_DP), "lon": round(lon, COORD_DP),
            "location_source": f"osm:{best['osm']}" if best else "approximate",
        })
    ids = [r["station_id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate station ids"

    w, s_, e, n = city["map"]["bounds"]
    pts = MultiPoint([Point(r["lon"], r["lat"]) for r in rows])
    area = unary_union([unary_union(list(ward_geoms.values())), pts.convex_hull.buffer(0.015)]).intersection(
        box(w, s_, e, n))
    cells_ = list(voronoi_polygons(pts, extend_to=box(w, s_, e, n)).geoms)
    feats = []
    for r in rows:
        p = Point(r["lon"], r["lat"])
        cell = next(c for c in cells_ if c.contains(p))
        poly = _multi(cell.intersection(area).simplify(0.0001, preserve_topology=True))
        ward = next((no for no, g in ward_geoms.items() if g.contains(p)), None)
        r["zone"] = next((f["properties"]["zone"] for f in ward_feats if f["properties"]["ward_no"] == ward), None)
        r["ward_no"] = ward
        r.update(cells(r["lat"], r["lon"]))
        feats.append({"type": "Feature", "properties": {**r, "synthetic_jurisdiction": True},
                      "geometry": _round_geom(poly)})
    feats.sort(key=lambda f: f["properties"]["station_id"])
    write_geojson(pack / "stations.geojson", feats)
    return feats


# ---------- POIs ----------
POI_TYPES = [  # (tag, value, poi_type); first match wins
    ("amenity", "atm", "atm"), ("amenity", "bank", "bank"), ("amenity", "bar", "bar"), ("amenity", "pub", "bar"),
    ("amenity", "hospital", "hospital"), ("amenity", "clinic", "clinic"), ("amenity", "marketplace", "market"),
    ("amenity", "fuel", "fuel"), ("amenity", "bus_station", "bus_station"), ("amenity", "school", "school"),
    ("amenity", "college", "college"), ("amenity", "cinema", "cinema"), ("amenity", "restaurant", "restaurant"),
    ("amenity", "cafe", "cafe"), ("amenity", "pharmacy", "pharmacy"), ("amenity", "parking", "parking"),
    ("shop", "jewelry", "jeweller"), ("shop", "mall", "mall"), ("shop", "supermarket", "supermarket"),
    ("shop", "mobile_phone", "mobile_shop"), ("shop", "electronics", "electronics"),
    ("shop", "pawnbroker", "pawnbroker"), ("highway", "bus_stop", "bus_stop"), ("tourism", "hotel", "hotel"),
]
RELIGION = {"hindu": "temple", "christian": "church", "muslim": "mosque"}


def poi_type(t: dict) -> str | None:
    if t.get("amenity") == "place_of_worship":
        return RELIGION.get(t.get("religion", ""), "place_of_worship")
    if t.get("railway") == "station" or t.get("public_transport") == "station":
        metro = t.get("station") == "subway" or "metro" in (t.get("name", "") + t.get("network", "")).lower()
        return "metro_station" if metro else "railway_station"
    for k, v, typ in POI_TYPES:
        if t.get(k) == v:
            return typ
    return None


def build_pois(out: Path) -> int:
    els = json.loads((RAW / "osm_pois.json").read_text(encoding="utf-8"))["elements"]
    rows, seen = [], set()
    for e in sorted(els, key=lambda x: (x["type"], x["id"])):
        t = e.get("tags", {})
        typ = poi_type(t)
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        key = f"{e['type']}/{e['id']}"
        if typ is None or lat is None or key in seen:
            continue
        seen.add(key)
        rows.append({"poi_id": f"osm:{key}", "poi_type": typ, "name": t.get("name:en") or t.get("name"),
                     "lat": round(lat, COORD_DP), "lon": round(lon, COORD_DP), **cells(lat, lon),
                     "source": "openstreetmap", "licence": "ODbL-1.0", "synthetic": False})
    with tempfile.TemporaryDirectory() as td:
        nd = Path(td) / "pois.ndjson"
        nd.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        con = duckdb.connect()
        con.execute(f"COPY (SELECT * FROM read_json_auto('{nd.as_posix()}') ORDER BY poi_id) "
                    f"TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        con.close()
    return len(rows)


TEXT_SUFFIXES = {".csv", ".geojson", ".json", ".yaml"}


def sha256(p: Path) -> str:
    """Hash with LF line endings for text files, so Windows and Linux checkouts agree."""
    b = p.read_bytes()
    if p.suffix in TEXT_SUFFIXES:
        b = b.replace(b"\r\n", b"\n")
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="chennai")
    args = ap.parse_args()
    pack = ROOT / "cities" / args.city
    city = yaml.safe_load((pack / "city.yaml").read_text(encoding="utf-8"))
    src = yaml.safe_load((pack / "sources.yaml").read_text(encoding="utf-8"))

    ward_feats, ward_geoms = build_wards(pack, src["wards"])
    stations = build_stations(pack, ward_feats, ward_geoms, city)
    pois_path = REF / "osm_pois.parquet"
    n_pois = build_pois(pois_path)

    outputs = [pack / "wards.geojson", pack / "stations.geojson", pois_path,
               pack / "law_sections.csv", pack / "calendar.csv"]
    manifest = {
        "city": args.city,
        "counts": {"wards": len(ward_feats), "stations": len(stations), "pois": n_pois,
                   "stations_osm_located": sum(1 for f in stations
                                               if f["properties"]["location_source"].startswith("osm:")),
                   "law_sections": sum(1 for _ in csv.DictReader((pack / "law_sections.csv").open(encoding="utf-8"))),
                   "calendar_days": sum(1 for _ in csv.DictReader((pack / "calendar.csv").open(encoding="utf-8")))},
        "sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in outputs},
    }
    (REF / "MANIFEST.json").write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps(manifest["counts"]))


if __name__ == "__main__":
    main()
