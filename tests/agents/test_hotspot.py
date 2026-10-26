"""Hotspot detector (WS2-18, spec E3 / LNK-05): statistics only, reads only q_hex_counts (R1)."""

import math
from datetime import date, timedelta

import pytest

from app.agents.hotspot import BASELINE_WINDOWS, ROW_LIMIT, detect_hotspots, poisson_sf
from app.tracing import Tracer

SINCE, UNTIL = "2026-10-19", "2026-10-26"


class FakeDeps:
    def __init__(self, rows, tmp_path):
        self.rows = rows
        self.calls = []
        self.tracer = Tracer("t", tmp_path, echo=False)

    def query(self, name, *, agent, **params):
        self.calls.append((name, agent, params))
        return self.rows, "qid-1"


def _rows():
    start = date.fromisoformat(SINCE)
    rows = []

    def add(cell, cat, d, n, station):
        ids = [f"CHN-{len(rows):03d}-{i}" for i in range(n)]
        rows.append({"cell": cell, "category": cat, "day": d.isoformat(), "n": n, "crime_ids": ids,
                     "station_ids": [station]})

    # Baseline: 8 prior weeks. Cell A: ~1 snatching a week. Cell B: steady 4 thefts a week.
    for w in range(1, BASELINE_WINDOWS + 1):
        wk = start - timedelta(days=7 * w)
        add("89a", "chain_snatching", wk + timedelta(days=2), 1, "PS-ADYAR")
        add("89b", "vehicle_theft", wk + timedelta(days=1), 4, "PS-GUINDY")
    # Window: cell A spikes to 9 snatchings (two stations); cell B stays at 4; new cell C gets 4.
    for i in range(9):
        add("89a", "chain_snatching", start + timedelta(days=i % 7), 1, "PS-ADYAR" if i % 2 else "PS-VELACHERY")
    add("89b", "vehicle_theft", start + timedelta(days=3), 4, "PS-GUINDY")
    add("89c", "chain_snatching", start + timedelta(days=4), 4, "PS-MYLAPORE")
    return rows


def test_poisson_tail_matches_closed_form():
    assert poisson_sf(0, 3.0) == 1.0
    assert poisson_sf(1, 1.0) == pytest.approx(1 - math.exp(-1))
    assert poisson_sf(3, 2.0) == pytest.approx(1 - math.exp(-2) * (1 + 2 + 2))


def test_spike_is_a_high_hotspot_and_steady_cell_is_not(tmp_path):
    deps = FakeDeps(_rows(), tmp_path)
    out = detect_hotspots(deps, since=SINCE, until=UNTIL)
    by_cell = {h["cell"]: h for h in out}
    assert "89b" not in by_cell                     # 4 vs 4 expected: nothing unusual
    a = by_cell["89a"]
    assert a["band"] == "high" and a["observed"] == 9 and a["expected"] < 2
    assert a["kind"] == "hotspot" and a["status"] == "pending" and a["factors"] == []
    assert 0.99 <= a["score"] <= 1 and len(a["crimes"]) == 9
    assert a["stations"] == ["PS-ADYAR", "PS-VELACHERY"]
    assert "9 chain snatching crimes in cell 89a" in a["rationale"] and "expected" in a["rationale"]
    assert "alert_id" not in a and "run_id" not in a
    assert a["window"] == {"since": SINCE, "until": UNTIL} and a["zetaris_query_ids"] == ["qid-1"]


def test_new_cell_is_judged_against_the_citywide_prior(tmp_path):
    out = detect_hotspots(FakeDeps(_rows(), tmp_path), since=SINCE, until=UNTIL)
    c = next(h for h in out if h["cell"] == "89c")
    assert c["band"] in ("medium", "high") and c["observed"] == 4


def test_reads_only_q_hex_counts_with_the_baseline_range(tmp_path):
    deps = FakeDeps(_rows(), tmp_path)
    detect_hotspots(deps, since=SINCE, until=UNTIL)
    ((name, agent, params),) = deps.calls
    assert name == "q_hex_counts" and agent == "Hotspot detector"
    assert params == {"since": SINCE, "until": UNTIL, "baseline_since": "2026-08-24", "limit": ROW_LIMIT}


def test_cells_filter_and_ordering(tmp_path):
    out = detect_hotspots(FakeDeps(_rows(), tmp_path), since=SINCE, until=UNTIL, cells=["89c"])
    assert [h["cell"] for h in out] == ["89c"]
    allh = detect_hotspots(FakeDeps(_rows(), tmp_path), since=SINCE, until=UNTIL)
    assert [h["p_value"] for h in allh] == sorted(h["p_value"] for h in allh)


def test_trace_event_and_bad_window(tmp_path):
    deps = FakeDeps(_rows(), tmp_path)
    detect_hotspots(deps, since=SINCE, until=UNTIL)
    (ev,) = [e for e in deps.tracer.read() if e["action"] == "detect_hotspots"]
    assert ev["agent_name"] == "Hotspot detector" and ev["zetaris_query_ids"] == ["qid-1"] and ev["model"] is None
    with pytest.raises(ValueError):
        detect_hotspots(deps, since=UNTIL, until=SINCE)


def test_quiet_city_gives_no_hotspots(tmp_path):
    assert detect_hotspots(FakeDeps([], tmp_path), since=SINCE, until=UNTIL) == []


def test_end_to_end_through_the_duckdb_twin(tmp_path):
    """The real q_hex_counts sample SQL, run by ZetarisClient in sample mode over a v_crime_unified table."""
    import duckdb

    from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient
    from app.agents.base import AgentDeps
    from app.config import Settings

    assert NAMED_QUERIES["q_hex_counts"].columns == ("cell", "category", "day", "n", "crime_ids", "station_ids")
    settings = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    tracer = Tracer("t", tmp_path, echo=False)
    client = ZetarisClient(settings, tracer=tracer)
    client._duck = duckdb.connect(":memory:")
    client._duck.execute("CREATE TABLE v_crime_unified (crime_id VARCHAR, station_id VARCHAR, category VARCHAR, "
                         "occurred_from TIMESTAMP, h3_r9 VARCHAR, synthetic BOOLEAN)")
    values = []
    for r in _rows():
        for i, cid in enumerate(r["crime_ids"]):
            values.append((cid, r["station_ids"][0], r["category"], f"{r['day']} 1{i % 10}:00:00", r["cell"], True))
    client._duck.executemany("INSERT INTO v_crime_unified VALUES (?, ?, ?, ?, ?, ?)", values)
    deps = AgentDeps(tracer=tracer, zetaris=client, nightshift=None)
    out = detect_hotspots(deps, since=SINCE, until=UNTIL)
    a = next(h for h in out if h["cell"] == "89a")
    assert a["band"] == "high" and a["observed"] == 9 and len(a["crimes"]) == 9
    assert a["stations"] == ["PS-ADYAR", "PS-VELACHERY"]
    assert "89b" not in {h["cell"] for h in out}
    q = [e for e in tracer.read() if e["action"] == "zetaris_query"]
    assert q and q[0]["input_summary"] == "q_hex_counts" and "via=sample" in q[0]["output_summary"]
