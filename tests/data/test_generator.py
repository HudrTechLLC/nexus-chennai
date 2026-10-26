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
    assert {r["label"] for r in rows} == {"series", "decoy", "duplicate", "vehicle_chain", "offender_return"}
    assert all(r["crime_a"] < r["crime_b"] for r in rows)


def _blocks(a: dict, b: dict) -> bool:
    from datetime import datetime

    da = datetime.fromisoformat(a["occurred_from"])
    db = datetime.fromisoformat(b["occurred_from"])
    return abs((da - db).days) <= 45 and gh5_block(geohash(a["lat"], a["lon"]), geohash(b["lat"], b["lon"]))


# ---------- slice 2 ----------
import duckdb  # noqa: E402

from app.models import AnprRead, CallLog, CctvCamera, HistorySheet, LegacyCctnsRow, Release  # noqa: E402
from app.scoring.factors import plate_match  # noqa: E402


def _parquet(out: Path, pattern: str) -> list[dict]:
    con = duckdb.connect()
    cur = con.execute(f"SELECT * FROM read_parquet('{(out / pattern).as_posix()}')")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _csv(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


def test_hero_anpr_sightings_match_the_spec(out):
    reads = {r["camera_id"]: r for r in _parquet(out, "anpr/reads_*.parquet") if r["plate_text"] == "TN09BX4471"
             and r["crime_id"] in ("CHN-AD-2026-001182", "CHN-VL-2026-000877")}
    from datetime import timezone

    utc = reads["ANPR-OMR-12"]["read_at"].astimezone(timezone.utc)
    assert utc.isoformat().startswith("2026-10-14T14:28:41")  # 19:58:41 IST
    assert abs(reads["ANPR-OMR-12"]["plate_confidence"] - 0.81) < 1e-9
    assert "ANPR-VLY-03" in reads


def test_slice2_rows_validate_against_d3_models(out):
    for r in _parquet(out, "anpr/reads_*.parquet")[:500]:
        AnprRead.model_validate({k: r[k] for k in AnprRead.model_fields})
    for r in _parquet(out, "calls/calls_*.parquet")[:500]:
        CallLog.model_validate({k: r[k] for k in CallLog.model_fields if k != "location"}
                               | {"location": {"lat": r["lat"], "lon": r["lon"]}})
    for r in _csv(out / "ref/cctv_cameras.csv")[:500]:
        CctvCamera.model_validate({k: r[k] for k in CctvCamera.model_fields})
    for r in _csv(out / "ref/releases.csv"):
        Release.model_validate({k: (r[k] or None) for k in Release.model_fields})
    for r in _csv(out / "ref/history_sheets.csv")[:300]:
        HistorySheet.model_validate({k: (r[k] or None) for k in HistorySheet.model_fields})
    files = sorted((out / "legacy").glob("cctns_*.csv"))
    assert len(files) == 8
    for f in files:
        rows = _csv(f)
        assert list(rows[0]) == list(LegacyCctnsRow.model_fields)
        for r in rows[:50]:
            LegacyCctnsRow.model_validate(r)
    assert _parquet(out, "legacy/archive.parquet")


def test_vehicle_chains_are_traceable_on_anpr(crimes, out):
    chains = json.loads((out / "_truth/vehicle_chains.json").read_text(encoding="utf-8"))
    assert len(chains) == 12
    reads = _parquet(out, "anpr/reads_*.parquet")
    by_plate = defaultdict(list)
    for r in reads:
        by_plate[r["plate_text"]].append(r)
    vehicles = defaultdict(list)
    for v in jl(out / "supabase" / "crime_vehicles.jsonl"):
        vehicles[v["crime_id"]].append(v)
    for c in chains:
        full = c["plate"].replace(" ", "")
        assert len(by_plate[full]) >= 3
        theft, use = crimes[c["theft_crime_id"]], crimes[c["use_crime_ids"][0]]
        assert theft["station_id"] != use["station_id"] and theft["occurred_from"] < use["occurred_from"]
        seen = [v["plate_display"] for v in vehicles[use["crime_id"]] if v["role"] == "used_by_offender"]
        assert seen and (plate_match(seen[0], c["plate"]) or 0) > 0


def test_offender_returns_follow_release_near_home(crimes, out):
    rets = json.loads((out / "_truth/offender_returns.json").read_text(encoding="utf-8"))
    rel = {r["release_id"]: r for r in _csv(out / "ref/releases.csv")}
    assert len(rets) == 10
    from datetime import date, datetime

    for x in rets:
        released = date.fromisoformat(rel[x["release_id"]]["released_on"])
        for cid in x["return_crime_ids"]:
            days = (datetime.fromisoformat(crimes[cid]["occurred_from"]).date() - released).days
            assert 0 < days <= 60
        assert x["prior_case_refs"], x["return_id"]


def test_dq_defects_planted(out):
    dq = json.loads((out / "_truth/dq.json").read_text(encoding="utf-8"))
    rules = {d["rule"] for d in dq}
    assert {"dq_bad_geo", "dq_time_inconsistent", "dq_unmapped_sections", "dq_stale_cameras"} <= rules


def test_map_projections_are_aggregates(out):
    cells = jl(out / "supabase" / "map_call_cells.jsonl")
    assert cells and set(cells[0]) == {"h3_r9", "category", "hour_bucket", "n", "synthetic"}
    reads = jl(out / "supabase" / "map_anpr_reads.jsonl")
    assert reads and all(r["crime_id"] for r in reads)


def test_tips_mix_unscreened_and_corroborating(crimes, out):
    import re
    from collections import Counter

    from app.models.public import Tip

    tips = jl(out / "supabase" / "tips.jsonl")
    truth = {t["tip_id"]: t for t in json.loads((out / "_truth" / "tips.json").read_text(encoding="utf-8"))}
    assert len(tips) == 40 and set(truth) == {t["tip_id"] for t in tips}
    assert Counter(t["kind"] for t in truth.values()) == {"corroborating": 24, "unrelated": 6, "injection": 4,
                                                          "emergency": 2, "spam": 4}
    for t in tips:
        Tip.model_validate({k: t[k] for k in Tip.model_fields if k in t})
        assert re.fullmatch(r"TIP-[A-HJ-NP-Z2-9]{8}", t["tip_id"])
        assert t["guard"] is None and t["status"] == "new" and t["tip_code_hash"] is None and t["synthetic"]
        assert t["category"] in ("vehicle_seen", "person_seen", "have_cctv", "item_for_sale", "something_else")
        assert t["approx_cell"] is None or re.fullmatch(r"88[0-9a-f]{13}", t["approx_cell"])
    red = [t for t in tips if truth[t["tip_id"]]["series_id"] == "SER-RED-PULSAR"]
    assert len(red) == 6
    for t in red:  # each sighting sits in the cell of the crime it corroborates
        assert t["approx_cell"] == crimes[truth[t["tip_id"]]["crime_ids"][0]]["h3_r8"]
    assert any("Pulsar" in t["text"] for t in red)
