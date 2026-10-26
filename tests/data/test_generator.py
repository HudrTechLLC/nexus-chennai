"""Generator slice 1 (WS1-08): deterministic, model-valid, planted structure passes blocking.

Runs a small-scale generation (background scaled down; every planted item stays whole).
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest

from app.models import Crime, WitnessStatement
from data.generator.cli import generate
from data.geo import geohash, gh5_block

SCALE = 0.02


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("gen")
    generate(42, p, scale=SCALE)
    return p


def jl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture(scope="module")
def crimes(out) -> dict[str, dict]:
    return {c["crime_id"]: c for c in jl(out / "supabase" / "crimes.jsonl")}


def test_deterministic(out, tmp_path):
    again = tmp_path / "again"
    m2 = generate(42, again, scale=SCALE)
    m1 = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m1["sha256"] == m2["sha256"]


def test_different_seed_differs(out, tmp_path):
    m = generate(7, tmp_path / "s7", scale=SCALE)
    m1 = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["sha256"]["supabase/crimes.jsonl"] != m1["sha256"]["supabase/crimes.jsonl"]


def test_hero_pair_is_the_spec_example(crimes, out):
    a, b = crimes["CHN-AD-2026-001182"], crimes["CHN-VL-2026-000877"]
    assert (a["station_id"], a["fir_no"]) == ("PS-ADYAR-J2", "1182/2026")
    assert (b["station_id"], b["fir_no"]) == ("PS-VELACHERY-J7", "877/2026")
    assert a["occurred_from"] == "2026-10-14T19:40:00+05:30"
    assert "TN 09 ?? 4471" in a["narrative"] and "red Bajaj Pulsar 150" in a["narrative"]
    series = {s["series_id"]: s for s in json.loads((out / "_truth/series.json").read_text(encoding="utf-8"))}
    assert {a["crime_id"], b["crime_id"]} <= set(series["SER-RED-PULSAR"]["crime_ids"])


def test_rows_validate_against_d3_models(crimes, out):
    vehicles = defaultdict(list)
    for v in jl(out / "supabase" / "crime_vehicles.jsonl"):
        vehicles[v["crime_id"]].append({"role": v["role"], "type": v["vehicle_type"], "make_model": v["make_model"],
                                        "colour": v["colour"], "plate": v["plate_display"]})
    for c in crimes.values():
        loc = {"lat": c["lat"], "lon": c["lon"], "address": c["address"], "ward": c["ward_no"],
               "h3_r9": c["h3_r9"], "geohash7": c["geohash7"]}
        row = {k: c[k] for k in ("crime_id", "source", "source_row_id", "station_id", "fir_no", "category",
                                 "sub_type", "sections", "occurred_from", "occurred_to", "reported_at", "severity",
                                 "property", "weapon", "victims", "status", "synthetic", "narrative")}
        Crime.model_validate(row | {"location": loc, "vehicles": vehicles[c["crime_id"]],
                                    "offenders_described": c["offenders_described"]})
    for s in jl(out / "supabase" / "statements.jsonl"):
        WitnessStatement.model_validate({k: s[k] for k in WitnessStatement.model_fields})


def test_db_constraints_hold(crimes, out):
    wards = {w["ward_no"] for w in jl(out / "supabase" / "wards.jsonl")}
    stations = {s["station_id"] for s in jl(out / "supabase" / "stations.jsonl")}
    bns = {r["bns_code"] for r in jl(out / "supabase" / "section_map.jsonl")}
    seen = set()
    for c in crimes.values():
        assert c["synthetic"] is True
        assert c["station_id"] in stations and (c["ward_no"] is None or c["ward_no"] in wards)
        assert (c["station_id"], c["fir_no"]) not in seen
        seen.add((c["station_id"], c["fir_no"]))
        assert 1 <= c["severity"] <= 5 and c["occurred_to"] >= c["occurred_from"]
        assert all(s["code"] in bns for s in c["sections"])
        assert len(c["week"]) == 8 and c["week"][4:6] == "-W"


def test_series_chain_through_blocking(crimes, out):
    for s in json.loads((out / "_truth/series.json").read_text(encoding="utf-8")):
        members = [crimes[i] for i in s["crime_ids"]]
        assert len(s["stations"]) >= 2, s["series_id"]
        for m in members:
            others = [o for o in members if o is not m]
            assert any(_blocks(m, o) for o in others), (s["series_id"], m["crime_id"])


def test_decoys_pass_blocking_but_differ(crimes, out):
    series = {s["series_id"]: s for s in json.loads((out / "_truth/series.json").read_text(encoding="utf-8"))}
    decoys = json.loads((out / "_truth/decoys.json").read_text(encoding="utf-8"))
    assert len(decoys) == 25
    blocked = 0
    for d in decoys:
        members = [crimes[i] for i in series[d["shadows_series_id"]]["crime_ids"]]
        for cid in d["crime_ids"]:
            blocked += any(_blocks(crimes[cid], m) for m in members)
            assert crimes[cid]["category"] == members[0]["category"]
    assert blocked >= 0.9 * sum(len(d["crime_ids"]) for d in decoys)


def test_duplicates_two_stations_same_incident(crimes, out):
    dups = json.loads((out / "_truth/duplicates.json").read_text(encoding="utf-8"))
    assert len(dups) == 15
    for d in dups:
        a, b = (crimes[i] for i in d["crime_ids"])
        assert a["station_id"] != b["station_id"] and a["category"] == b["category"]


def test_pairs_labels(out):
    rows = list(csv.DictReader((out / "_truth/pairs.csv").open(encoding="utf-8")))
    assert {r["label"] for r in rows} == {"series", "decoy", "duplicate"}
    assert all(r["crime_a"] < r["crime_b"] for r in rows)


def _blocks(a: dict, b: dict) -> bool:
    from datetime import datetime

    da = datetime.fromisoformat(a["occurred_from"])
    db = datetime.fromisoformat(b["occurred_from"])
    return abs((da - db).days) <= 45 and gh5_block(geohash(a["lat"], a["lon"]), geohash(b["lat"], b["lon"]))
