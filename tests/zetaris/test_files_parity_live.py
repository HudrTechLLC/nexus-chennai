"""Live parity (WS1-19): every named query gives the same answer on the file store (ZETARIS_DATA=files) as on
the hosted Supabase source, for the judge cases and the hero pair.

Runs only with NEXUS_LIVE=1 and a Zetaris key file, after `python -m data.setup_live` (or, on our box, after
nexus_fs / nexusfs were registered). It is light, sequential and read-only; run it when no lane is live.

Parity is defined on generator rows. Our Supabase also holds rows filed in the console (FIRs, statements,
uploads), which a judge's file store never has, so any sb row that mentions a console crime id is dropped
before comparing. JSON text is compared parsed, and numbers with a small tolerance.
q_station_matrix reads link_alerts, which is runtime data: on files it starts empty (checked as such).
"""

from __future__ import annotations

import json
import math
import uuid
import os
from pathlib import Path

import pytest

from app.adapters.zetaris import ZetarisClient
from app.adapters.zetaris_queries_n2 import cases_params
from app.config import Settings
from app.tracing import Tracer

KEY = Path(os.path.expanduser(os.environ.get("ZETARIS_API_KEY_FILE", "~/.secrets/nexus-zetaris.key")))
pytestmark = pytest.mark.skipif(os.environ.get("NEXUS_LIVE") != "1" or not KEY.is_file(), reason="live Zetaris only")

JUDGE = ["CHN-AD-2026-001182", "CHN-KU-2025-000078", "CHN-GU-2025-000945"]
HERO_PAIR = "CHN-VL-2026-000877"
# Queries without an ORDER BY or with an unsorted collect_list: compare as sorted rows with sorted id lists.
UNORDERED = {"q_hex_counts"}
SINCE, UNTIL = "2026-09-25", "2026-10-26"


def _cases() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for cid in JUDGE + [HERO_PAIR]:
        out += [("q_case", {"crime_id": cid}), ("q_features", {"ids": cid}), ("q_tip_corroboration", {"crime_id": cid}),
                ("q_calls_near", {"crime_id": cid}), ("q_news", {"crime_id": cid}), ("q_context", {"crime_id": cid})]
        out += [("q_candidates", {"crime_id": cid, "days": 45, "ring": r}) for r in (3, 6, 10)]
    out += [
        ("q_cases", cases_params(sorted(JUDGE + [HERO_PAIR]))[0]),
        ("q_vehicle_trail", {"plate_pattern": "TN 09 ?? 4471", "t0": "2026-10-14T19:40:00+05:30",
                             "t1": "2026-10-16T19:55:00+05:30", "cells": ""}),
        ("q_offender_return", {"mo_tags": "night_house_break,back_door_pried", "ward": 5,
                               "since": "2025-08-19T02:00:00+05:30"}),
        ("q_search", {"category": "chain_snatching", "pattern": "red", "since": SINCE, "until": UNTIL,
                      "station_id": "", "status": ""}),
        ("q_hex_counts", {"baseline_since": "2026-08-01", "until": UNTIL}),
        ("q_dq_flags", {"ids": ",".join(JUDGE + [HERO_PAIR])}),
    ]
    return out


@pytest.fixture(scope="module")
def clients(tmp_path_factory):
    key = KEY.read_text(encoding="utf-8").strip()
    t = Tracer("parity", tmp_path_factory.mktemp("t"), echo=False)
    return {d: ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key=key, zetaris_data=d,
                                    zetaris_timeout_seconds=300.0), tracer=t)
            for d in ("supabase", "files")}


@pytest.fixture(scope="module")
def console_ids(clients) -> set[str]:
    """Crime ids on our Supabase that the generator did not make (filed in the console)."""
    fs = {r[0] for r in clients["files"]._post("SELECT crime_id FROM nexus_fs.crimes ORDER BY crime_id", str(uuid.uuid4()), 100000)}
    sb = {r[0] for r in clients["supabase"]._post("SELECT crime_id FROM sb.crimes ORDER BY crime_id", str(uuid.uuid4()), 100000)}
    assert fs <= sb, sorted(fs - sb)[:5]
    return sb - fs


def _norm(v):
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return _norm(json.loads(v))
        except ValueError:
            return v
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, str):
        try:
            f = float(v)
            return f if math.isfinite(f) and any(c in v for c in ".eE") else v
        except ValueError:
            return v
    return v


def _close(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    return a == b


@pytest.mark.parametrize("name,params", _cases(), ids=lambda x: x if isinstance(x, str) else "")
def test_named_query_matches_on_files(clients, console_ids, name, params):
    sb = clients["supabase"].named(name, agent="parity", limit=5000, **params)
    fs = clients["files"].named(name, agent="parity", limit=5000, **params)
    assert sb.source == fs.source == "zetaris"
    keep = [r for r in sb.rows if not any(cid in json.dumps(r) for cid in console_ids)]
    a, b = [_norm(r) for r in keep], [_norm(r) for r in fs.rows]
    if name in UNORDERED:
        def canon(rows):
            return sorted((["," .join(sorted(x.split(","))) if isinstance(x, str) and "," in x else x for x in r]
                           for r in rows), key=json.dumps)
        a, b = canon(a), canon(b)
    assert len(a) == len(b), f"{name}: {len(a)} rows on sb (generator rows) vs {len(b)} on files"
    bad = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if not _close(x, y)]
    assert not bad, f"{name}: first difference at row {bad[0][0]}:\n sb={str(bad[0][1])[:600]}\n fs={str(bad[0][2])[:600]}"


def test_station_matrix_is_empty_on_files_by_construction(clients):
    assert clients["files"].named("q_station_matrix", agent="parity", since=SINCE, until=UNTIL).rows == []


def test_dq_summary_differs_only_by_console_rows(clients, console_ids):
    sb = dict(clients["supabase"].named("q_dq_summary", agent="parity").rows)
    fs = dict(clients["files"].named("q_dq_summary", agent="parity").rows)
    assert sb.keys() == fs.keys()
    # stale cameras and unmapped legacy sections never involve a console row; the rest may, by at most
    # a couple of rows per console crime (a duplicate pair counts both directions).
    for rule in ("stale_camera", "unmapped_section", "bad_geo", "time_inconsistent"):
        assert sb[rule] == fs[rule], rule
    for rule in sb:
        assert 0 <= int(sb[rule]) - int(fs[rule]) <= 2 * max(len(console_ids), 1) + 6, rule


STRICT_IDS = ["CHN-AD-2026-001182", HERO_PAIR, "CHN-KU-2025-000078", "CHN-GU-2025-000945"]  # KU = house break


def test_q_cases_text_forms_match_live_exactly(clients):
    """One q_cases read feeds the Planner, D-033 (narrative) and series naming (sub_type, category, station_id,
    vehicles, features.mo): every column must be the same TEXT as live, not just the same parsed value."""
    params = cases_params(sorted(STRICT_IDS))[0]
    sb = {r[0]: r for r in clients["supabase"].named("q_cases", agent="parity", **params).rows}
    fs = {r[0]: r for r in clients["files"].named("q_cases", agent="parity", **params).rows}
    cols = clients["files"].registry["q_cases"].columns
    assert set(STRICT_IDS) <= set(sb) and set(STRICT_IDS) <= set(fs)
    bad = [(cid, c, sb[cid][i], fs[cid][i]) for cid in STRICT_IDS for i, c in enumerate(cols) if sb[cid][i] != fs[cid][i]]
    assert not bad, "\n".join(f"{cid}.{c}:\n sb={str(a)[:300]}\n fs={str(b)[:300]}" for cid, c, a, b in bad[:5])


def test_tip_corroboration_on_files_returns_summary_and_week(clients):
    rows = clients["files"].named("q_tip_corroboration", agent="parity", crime_id="CHN-AD-2026-001182").dicts()
    assert rows, "hero tip corroboration is empty on files"
    assert all(r["summary"] and r["received_week"] for r in rows)
