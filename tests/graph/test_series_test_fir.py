"""D-033: test FIRs are never series members; a series drops a stored test FIR, and nothing else."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_worker_store import FakeSB  # noqa: E402

from app.agents import MemoryStore, detect_series  # noqa: E402
from app.agents.series import TEST_FIR_REASON, find_test_firs, is_test_fir  # noqa: E402
from app.graph.runner import _detect_series, _save_series  # noqa: E402
from app.graph.store import SupabaseStore  # noqa: E402
from app.tracing import Tracer  # noqa: E402

NARRATIVES = {
    "A": "Two men on a red two-wheeler snatched a chain.",
    "B": "Chain snatched by a pillion rider on a red bike.",
    "C": "Pillion rider pulled the victim's chain and fled.",
    "T": "[nexus-5 timing test FIR] Back door forced open with a crowbar.",
    "D": "Gold chain snatched near the bus stop.",
    "E": "Chain snatching, two men on a bike.",
    "F": "Rider snatched a mangalsutra and fled.",
}


def pair(x, y, status="pending"):
    return {"kind": "pair", "status": status, "crimes": [x, y], "alert_id": f"LA-{x}{y}", "score": 0.8,
            "stations": ["PS-1"]}


@pytest.mark.parametrize("text", [
    "[nexus-5 timing test FIR] back door forced", "  [TEST] smoke", "[Test-run 3] x", "[QA test] y",
])
def test_test_fir_label_matches(text):
    assert is_test_fir(text)


@pytest.mark.parametrize("text", [
    "Victim said [test] later", "[testimony recorded] x", "[contest prize] y", "Test FIR without brackets",
    "[attested copy] z", "", None,
])
def test_ordinary_narratives_are_not_test_firs(text):
    assert not is_test_fir(text)


def test_excluded_crime_neither_joins_nor_bridges_a_series():
    alerts = [pair("A", "B"), pair("B", "C"), pair("B", "T"), pair("T", "D"), pair("D", "E"), pair("E", "F")]
    assert [s["crime_ids"] for s in detect_series(alerts)] == [["A", "B", "C", "D", "E", "F", "T"]]
    out = detect_series(alerts, excluded={"T"})
    assert sorted(s["crime_ids"] for s in out) == [["A", "B", "C"], ["D", "E", "F"]]


# ----- stores ---------------------------------------------------------------------------------------------


def only_t(ids):
    return {c: TEST_FIR_REASON for c in ids if c == "T"}


def test_memory_store_removes_only_flagged_members_and_is_idempotent():
    st = MemoryStore()
    st.write_series({"series_id": "SER-1", "crime_ids": ["A", "B", "C", "T", "X"]}, "run_1")
    st.write_series({"series_id": "SER-2", "crime_ids": ["A", "B", "C"]}, "run_2", exclude=only_t)
    assert st.series["SER-1"]["crime_ids"] == ["A", "B", "C", "X"]  # X was only unseen: kept
    assert st.removed == [{"series_id": "SER-1", "crime_id": "T", "reason": TEST_FIR_REASON}]
    st.write_series({"series_id": "SER-2", "crime_ids": ["A", "B", "C"]}, "run_3", exclude=only_t)
    assert len(st.removed) == 1 and st.series["SER-1"]["crime_ids"] == ["A", "B", "C", "X"]


def test_supabase_store_deletes_only_this_series_rows_and_never_touches_crimes(tmp_path):
    sb = FakeSB({"series": [{"series_id": "SER-1", "status": "candidate"}],
                 "series_members": [{"series_id": "SER-1", "crime_id": c} for c in ("A", "B", "C", "T", "X")]
                 + [{"series_id": "SER-OTHER", "crime_id": "T"}],
                 "crimes": [{"crime_id": c, "narrative": n} for c, n in NARRATIVES.items()]})
    deleted = []
    sb.delete = lambda table, match: deleted.append((table, dict(match))) or sb.tables.__setitem__(
        table, [r for r in sb.tables[table] if not FakeSB._match(r, match)])
    store = SupabaseStore(sb, Tracer("r", tmp_path, echo=False))
    ser = {"series_id": "SER-NEW", "crime_ids": ["A", "B", "C"], "stations": []}
    assert store.write_series(ser, "run_1", exclude=only_t) == "SER-1"
    assert deleted == [("series_members", {"series_id": "eq.SER-1", "crime_id": "eq.T"})]
    members = {(m["series_id"], m["crime_id"]) for m in sb.tables["series_members"]}
    assert ("SER-OTHER", "T") in members and ("SER-1", "X") in members and ("SER-1", "T") not in members
    assert not any(t == "crimes" and op != "select" for op, t, _ in sb.log)
    assert len(sb.tables["crimes"]) == len(NARRATIVES)
    # a re-run with the same inputs removes nothing
    assert store.write_series(dict(ser), "run_2", exclude=only_t) == "SER-1"
    assert len(deleted) == 1 and store.removed == [{"series_id": "SER-1", "crime_id": "T",
                                                    "reason": TEST_FIR_REASON}]


# ----- runner: detection + save, traced -------------------------------------------------------------------


def graph_for(tmp_path, store, run_id="run_1", fail=False):
    calls = []

    def query(name, *, agent, **params):
        calls.append(name)
        if fail:
            raise RuntimeError("zetaris down")
        ids = [v for v in params.values() if v]
        return [{"crime_id": c, "narrative": NARRATIVES.get(c)} for c in ids], "qid"

    tracer = Tracer(run_id, tmp_path, echo=False)
    return SimpleNamespace(deps=SimpleNamespace(query=query, tracer=tracer, store=store)), calls


def events(tmp_path, run_id):
    path = Path(tmp_path) / f"trace-{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_excludes_and_removes_a_test_fir_and_a_rerun_removes_nothing(tmp_path):
    store = MemoryStore()
    store.write_series({"series_id": "SER-RP", "crime_ids": ["A", "B", "C", "T"]}, "old_run")  # before D-033
    alerts = [pair("A", "B"), pair("B", "C"), pair("C", "T")]
    for run_id in ("run_1", "run_2"):
        graph, _ = graph_for(tmp_path, store, run_id)
        series, excluded = _detect_series(graph, alerts)
        assert excluded == {"T": TEST_FIR_REASON} and [s["crime_ids"] for s in series] == [["A", "B", "C"]]
        assert _save_series(graph, series, excluded) == []
        assert series[0]["series_id"] == "SER-RP"  # same id: overlap reuse
    assert store.series["SER-RP"]["crime_ids"] == ["A", "B", "C"]
    ev1, ev2 = events(tmp_path, "run_1"), events(tmp_path, "run_2")
    assert [e["extra"] for e in ev1 if e["action"] == "series_member_excluded"] == [
        {"crime_id": "T", "reason": TEST_FIR_REASON}]
    assert [e["extra"] for e in ev1 if e["action"] == "series_member_removed"] == [
        {"series_id": "SER-RP", "crime_id": "T", "reason": TEST_FIR_REASON}]
    assert not [e for e in ev2 if e["action"] == "series_member_removed"]  # idempotent


def test_pair_alerts_are_not_changed(tmp_path):
    alerts = [pair("A", "B"), pair("B", "C"), pair("C", "T")]
    before = json.dumps(alerts, sort_keys=True)
    graph, _ = graph_for(tmp_path, MemoryStore())
    _detect_series(graph, alerts)
    assert json.dumps(alerts, sort_keys=True) == before


def test_unreadable_narratives_exclude_and_remove_nothing(tmp_path):
    store = MemoryStore()
    store.write_series({"series_id": "SER-RP", "crime_ids": ["A", "B", "C", "T"]}, "old_run")
    graph, _ = graph_for(tmp_path, store, fail=True)
    series, excluded = _detect_series(graph, [pair("A", "B"), pair("B", "C"), pair("C", "T")])
    assert excluded == {} and series[0]["crime_ids"] == ["A", "B", "C", "T"]
    assert find_test_firs(graph.deps, ["T"]) == {}
    assert any(e["action"] == "test_fir_check_failed" and e["status"] == "degraded"
               for e in events(tmp_path, "run_1"))


def test_no_series_means_no_narrative_read(tmp_path):
    graph, calls = graph_for(tmp_path, MemoryStore())
    assert _detect_series(graph, [pair("A", "B")]) == ([], {}) and calls == []
