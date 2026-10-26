"""D-031 live parity: every named query returns the same rows at the client's default limit as at a
limit far above any answer. Zetaris pushes the REST limit into the JDBC scan before filters it cannot
push down, so a query without a top ORDER BY can silently lose rows. Runs only with NEXUS_LIVE=1."""

import os
from pathlib import Path

import pytest

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient
from app.adapters.zetaris_queries_n2 import cases_params
from app.config import Settings
from app.tracing import Tracer

KEY = Path(os.path.expanduser(os.environ.get("ZETARIS_API_KEY_FILE", "~/.secrets/nexus-zetaris.key")))
pytestmark = pytest.mark.skipif(os.environ.get("NEXUS_LIVE") != "1" or not KEY.is_file(), reason="live Zetaris only")

HERO, VL = "CHN-AD-2026-001182", "CHN-VL-2026-000877"
INPUTS = {
    "q_case": {"crime_id": HERO},
    "q_cases": cases_params([HERO, VL])[0],
    "q_candidates": {"crime_id": HERO, "days": 45, "ring": 6},
    "q_features": {"ids": f"{HERO},{VL},CHN-KU-2025-000078"},
    "q_dq_flags": {"ids": "CHN-SM-2026-000097,CHN-SR-2025-000023,CHN-SR-2026-001042,CHN-TR-2026-000194,"
                          "CHN-TR-2026-000474"},
    "q_hex_counts": {"baseline_since": "2026-09-01", "until": "2026-10-26"},
    "q_tip_corroboration": {"crime_id": HERO},
    "q_vehicle_trail": {"plate_pattern": "TN 09 ?? 4471", "t0": "2026-10-14T19:40:00+05:30",
                        "t1": "2026-10-16T19:55:00+05:30", "cells": ""},
    "q_offender_return": {"mo_tags": "night_house_break,back_door_pried", "ward": 5, "since": "2025-08-19T02:00:00+05:30"},
    "q_calls_near": {"crime_id": HERO},
    "q_station_matrix": {"since": "2026-01-01", "until": "2026-10-26"},
    "q_search": {"category": "robbery", "pattern": "pulsar", "since": "2026-01-01", "until": "2026-10-26",
                 "station_id": "", "status": ""},
    "q_context": {"crime_id": HERO},
}
SMALL, LARGE = 1000, 50000
# Callers that pass their own limit (the answer is legitimately larger than the default page).
CALLER_LIMIT = {"q_hex_counts": 200_000}  # agents/hotspot.py ROW_LIMIT


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key=KEY.read_text().strip()),
                         tracer=Tracer("parity", tmp_path_factory.mktemp("t"), echo=False))


def test_every_query_with_parameters_has_an_input():
    assert set(NAMED_QUERIES) - {"q_ping", "q_news"} <= set(INPUTS)  # q_news needs the API up (40_feeds.sql)


@pytest.mark.parametrize("name", sorted(INPUTS))
def test_default_limit_equals_large_limit(client, name):
    lim = CALLER_LIMIT.get(name, SMALL)
    small = client.named(name, agent="parity", limit=lim, **INPUTS[name])
    large = client.named(name, agent="parity", limit=max(LARGE, 2 * lim), **INPUTS[name])
    assert small.source == large.source == "zetaris"
    assert len(large.rows) < lim, f"{name}: answer is larger than the limit its caller uses"
    assert sorted(map(tuple, small.rows), key=str) == sorted(map(tuple, large.rows), key=str), name


def test_hero_pair_survives_the_default_limit(client):
    rows = client.named("q_candidates", agent="parity", crime_id=HERO, days=45, ring=6).dicts()
    assert VL in {r["crime_id"] for r in rows}
