"""Test doubles for the agents: a scripted Zetaris and a scripted Nightshift.

They record every call so tests can assert that agents read only through named queries
and call models only on pinned lanes. Nothing here fakes a product output: tests feed
rows and model replies in, and check what the agents' own code does with them.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import pytest

from app.adapters.nightshift import LaneNotConfigured, ModelResult
from app.agents import AgentDeps, MemoryStore
from app.tracing import Tracer

# ---------------------------------------------------------------------------
# Data: the spec's Adyar <-> Velachery pair, plus an unrelated house-break.
# ---------------------------------------------------------------------------

ADYAR = {
    "crime_id": "CHN-AD-2026-001182", "station_id": "PS-ADYAR-J2", "category": "robbery",
    "sub_type": "chain_snatching", "occurred_from": "2026-10-14T19:40:00+05:30",
    "occurred_to": "2026-10-14T19:50:00+05:30", "lat": 13.0012, "lon": 80.2565, "ward": 173,
    "h3_r9": "8961abc", "address": "LB Road near Adyar bus depot", "weapon": None,
    "narrative": "Two men on a red motorcycle came from behind and snatched a gold chain from a woman at the bus stop.",
    "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "make_model": "Bajaj Pulsar 150",
                  "colour": "red", "plate": "TN 09 ?? 4471"}],
    "offenders_described": [{"count": 2, "helmet": "black with red stripe", "build": "thin", "age_band": "20-30"}],
    "statements": [], "evidence": [], "forensics": [], "synthetic": True,
}
VELACHERY = {
    **ADYAR, "crime_id": "CHN-VL-2026-000877", "station_id": "PS-VELACHERY-J7",
    "occurred_from": "2026-10-16T19:55:00+05:30", "occurred_to": "2026-10-16T20:00:00+05:30",
    "lat": 12.9790, "lon": 80.2209, "ward": 180, "h3_r9": "8961def", "address": "Velachery bus stand",
    "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "make_model": "Bajaj Pulsar 150",
                  "colour": "red", "plate": "TN09BX4471"}],
    "offenders_described": [{"count": 2, "helmet": "black helmet red stripe", "build": "thin", "age_band": "20-30"}],
}
HOUSEBREAK = {
    **ADYAR, "crime_id": "CHN-TN-2026-002210", "station_id": "PS-TNAGAR-R1", "category": "burglary",
    "sub_type": "house_break", "occurred_from": "2026-10-02T02:10:00+05:30", "lat": 13.0418, "lon": 80.2341,
    "vehicles": [], "offenders_described": [{"count": 1, "build": "heavy", "age_band": "40-50"}],
    "weapon": "grille cutter",
}

MO_SNATCH = {"approach": "two_wheeler_from_behind", "offender_count": 2, "target": "lone_pedestrian_woman",
             "target_item": "gold_chain", "escape": "two_wheeler_towards_main_road", "violence": "push",
             "time_band": "evening", "place_type": ["bus_stop"], "disguise": ["helmet"], "verbal": None}
FEATURES = {
    ADYAR["crime_id"]: {"crime_id": ADYAR["crime_id"], "mo": MO_SNATCH,
                        "visual_tags": ["red motorcycle", "black helmet red stripe"],
                        "entities": {"plates": ["TN09??4471"]}},
    VELACHERY["crime_id"]: {"crime_id": VELACHERY["crime_id"], "mo": MO_SNATCH,
                            "visual_tags": ["red motorcycle", "two riders"], "entities": {"plates": ["TN09BX4471"]}},
    HOUSEBREAK["crime_id"]: {"crime_id": HOUSEBREAK["crime_id"],
                             "mo": {"approach": "grille_cut", "offender_count": 1, "target": "locked_house",
                                    "target_item": "jewellery", "time_band": "night", "place_type": ["residential"]},
                             "visual_tags": ["grille cut"], "entities": {"plates": []}},
}
CRIMES = {c["crime_id"]: c for c in (ADYAR, VELACHERY, HOUSEBREAK)}


def as_row(d: dict[str, Any]) -> dict[str, Any]:
    """jsonb columns arrive from Zetaris as JSON text."""
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in d.items()}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeResult:
    name: str
    columns: tuple[str, ...]
    rows: list[list[Any]]
    query_id: str
    ms: int = 1
    source: str = "zetaris"

    def dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, r, strict=True)) for r in self.rows]


@dataclass
class FakeZetaris:
    """Named-query double. `handlers[name](params) -> list[dict]`; unknown names raise like the adapter."""

    handlers: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = field(default_factory=dict)
    calls: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def named(self, name: str, *, agent: str, limit: int = 1000, timeout_s: float | None = None,
              **params: Any) -> FakeResult:
        self.calls.append((name, agent, params))
        if name not in self.handlers:
            raise KeyError(f"'{name}' is not a registered named query")
        rows = self.handlers[name](params)
        cols = tuple(rows[0].keys()) if rows else ("crime_id",)
        return FakeResult(name, cols, [[r.get(c) for c in cols] for r in rows], f"q_{uuid.uuid4().hex[:6]}")


@dataclass
class FakeNightshift:
    """Model double. `responder(lane, messages, purpose) -> str` is the model's reply content."""

    responder: Callable[[str, list[dict[str, Any]], str], str]
    lanes: tuple[str, ...] = ("fast", "reason")
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def model_for(self, lane: str) -> str:
        if lane not in self.lanes:
            raise LaneNotConfigured(lane)
        return f"nvidia/test-{lane}"

    def chat(self, lane: str, messages: list[dict[str, Any]], *, agent: str, purpose: str = "", **params: Any):
        model = self.model_for(lane)
        self.calls.append((lane, agent, purpose))
        content = self.responder(lane, messages, purpose)
        return ModelResult(lane=lane, model=model, routed_model=model, content=content,
                           receipt_id=f"rcpt_{len(self.calls)}", replayed=False, latency_ms=1)


def default_handlers() -> dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]]:
    def q_case(p):
        c = CRIMES.get(p["crime_id"])
        return [as_row(c)] if c else []

    def q_features(p):
        ids = str(p["ids"]).split(",")
        return [as_row(FEATURES[i]) for i in ids if i in FEATURES]

    def q_candidates(p):
        return [{"crime_id": cid} for cid in CRIMES if cid != p["crime_id"]]

    def empty(p):
        return []

    def trail(p):
        return [{"read_id": "ANPR-1", "plate_text": "TN09BX4471", "crime_id": ADYAR["crime_id"]},
                {"read_id": "ANPR-2", "plate_text": "TN09BX4471", "crime_id": VELACHERY["crime_id"]}]

    return {"q_case": q_case, "q_features": q_features, "q_candidates": q_candidates, "q_vehicle_trail": trail,
            "q_offender_return": empty, "q_tip_corroboration": empty, "q_calls_near": empty, "q_news": empty,
            "q_context": empty, "q_dq_flags": empty, "q_hex_counts": empty}


class FakeHmem:
    def __init__(self, delta: float = 0.0):
        self.delta = delta
        self.pairs: list[dict[str, Any]] = []

    def adjust(self, pair):
        assert "a" in pair and "b" in pair  # the engine's expected shape
        self.pairs.append(pair)
        return {"delta": self.delta, "memory_ids": ["HM-1"] if self.delta else [], "reason": "test memory"}


class FakeEngines:
    def __init__(self, hmem=None, scout=None, wm=None):
        self.hmem = hmem
        self.scout_intent = scout
        self.world_model = wm


@pytest.fixture
def tracer(tmp_path):
    return Tracer("test_run", tmp_path, echo=False)


@pytest.fixture
def make_deps(tracer):
    def _make(responder=None, handlers=None, engines=None, lanes=("fast", "reason")):
        z = FakeZetaris(handlers if handlers is not None else default_handlers())
        n = FakeNightshift(responder or (lambda lane, m, p: "{}"), lanes=lanes)
        return AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=engines or FakeEngines(),
                         store=MemoryStore())
    return _make
