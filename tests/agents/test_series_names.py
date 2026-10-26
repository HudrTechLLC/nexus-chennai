"""Series names come from the members' dominant MO, in code (no model), and are deterministic."""

from __future__ import annotations

import json
import random
from types import SimpleNamespace

from app.agents import MemoryStore
from app.agents.base import series_name
from app.agents.series import describe_series
from app.graph.runner import _detect_series, _save_series
from app.tracing import Tracer


def row(cid, station, sub_type="chain_snatching", category="robbery", vtype="motorcycle", colour="red",
        role="used_by_offender", approach=None, as_text=True):
    vehicles = [{"role": role, "type": vtype, "plate": None, "make_model": "Bajaj Pulsar 150", "colour": colour}] \
        if vtype else []
    features = {"mo": {"approach": approach}} if approach else None
    return {"crime_id": cid, "station_id": station, "sub_type": sub_type, "category": category,
            "vehicles": json.dumps(vehicles) if as_text else vehicles,
            "features": json.dumps(features) if (as_text and features) else features,
            "narrative": "Chain snatched."}


RED_PULSAR = [row(f"C{i}", ["PS-ADYAR-J2", "PS-THIRUVANMIYUR-J6", "PS-VELACHERY-J7"][i % 3]) for i in range(9)]


def test_red_pulsar_reads_like_an_analyst_would_name_it():
    assert describe_series(RED_PULSAR) == "Red two-wheeler chain snatchings · 3 stations"


def test_the_name_does_not_depend_on_member_order_or_json_encoding():
    shuffled = RED_PULSAR[:]
    random.Random(7).shuffle(shuffled)
    decoded = [row(r["crime_id"], r["station_id"], as_text=False) for r in RED_PULSAR]
    assert describe_series(shuffled) == describe_series(decoded) == describe_series(RED_PULSAR)


def test_a_part_shows_only_when_more_than_half_share_it():
    mixed_colour = [row("A", "PS-1", colour="red"), row("B", "PS-1", colour="black"), row("C", "PS-1", colour="blue")]
    assert describe_series(mixed_colour) == "Two-wheeler chain snatchings · 1 station"
    half_vehicle = [row("A", "PS-1"), row("B", "PS-2"), row("C", "PS-2", vtype=None), row("D", "PS-2", vtype=None)]
    assert describe_series(half_vehicle) == "Chain snatchings · 2 stations"


def test_without_a_vehicle_the_dominant_approach_names_the_series():
    grille = [row(c, "PS-ANNA-NAGAR", sub_type="house_break", category="burglary", vtype=None,
                  approach="rear_window_grille_cut") for c in ("A", "B", "C")]
    assert describe_series(grille) == "House breaks (rear window grille cut) · 1 station"


def test_falls_back_to_category_and_then_to_none():
    cab = [row(c, "PS-1", sub_type=s, vtype="taxi", colour="white") for c, s in
           (("A", "cab_robbery"), ("B", "highway_robbery"), ("C", "auto_robbery"))]
    assert describe_series(cab) == "White cab robberies · 1 station"  # category: robbery -> robberies
    mixed = [row("A", "PS-1", sub_type="chain_snatching", category="robbery"),
             row("B", "PS-1", sub_type="house_break", category="burglary"),
             row("C", "PS-1", sub_type="vehicle_theft", category="theft")]
    assert describe_series(mixed) is None
    assert describe_series([]) is None


def test_victim_vehicles_do_not_name_a_series():
    rows = [row(c, "PS-1", role="victim") for c in ("A", "B", "C")]
    assert describe_series(rows) == "Chain snatchings · 1 station"


def test_series_name_prefers_the_descriptive_name_and_keeps_the_old_fallback():
    assert series_name({"crime_ids": ["A", "B", "C"], "stations": ["PS-1"], "name": "Red x"}) == \
        "Red x"
    assert series_name({"crime_ids": ["A", "B", "C"], "stations": ["PS-1"]}) == "3 linked cases (PS-1)"


def test_the_run_names_the_stored_series(tmp_path):
    rows = {r["crime_id"]: r for r in RED_PULSAR[:3]}

    def query(name, *, agent, **params):
        return [rows[v] for v in params.values() if v in rows], "qid"

    store = MemoryStore()
    graph = SimpleNamespace(deps=SimpleNamespace(query=query, tracer=Tracer("run_1", tmp_path, echo=False),
                                                 store=store))
    alerts = [{"kind": "pair", "status": "pending", "crimes": ["C0", "C1"], "stations": []},
              {"kind": "pair", "status": "pending", "crimes": ["C1", "C2"], "stations": []}]
    series, _ = _detect_series(graph, alerts)
    assert _save_series(graph, series) == []
    assert store.series[series[0]["series_id"]]["name"] == "Red two-wheeler chain snatchings · 3 stations"
