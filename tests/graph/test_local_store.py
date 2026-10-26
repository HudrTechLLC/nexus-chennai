"""WS2-22 LocalStore: file-backed results under data/local/ when Supabase is not configured (live mode).

Same contract as MemoryStore and SupabaseStore (series id reuse, D-033 removal, dossier only on a stored
series), plus what only a file store can do: results and features survive a restart.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))

from app.agents import MemoryStore  # noqa: E402
from app.config import Settings  # noqa: E402
from app.graph.local_store import LocalStore, store_kind  # noqa: E402
from app.graph.runner import default_store  # noqa: E402
from app.graph.store import SupabaseStore  # noqa: E402
from app.tracing import Tracer  # noqa: E402

SER = {"series_id": "SER-NEW", "crime_ids": ["C1", "C2", "C3"], "stations": ["PS-A", "PS-B"]}
FEATS = {"crime_id": "C1", "extractor_version": "mo-v4", "model": "m", "receipt_id": "r1",
         "mo": {"approach": "two-wheeler", "target": "chain"}, "visual_tags": ["red"],
         "entities": {"plates": [], "persons": [], "phones": []}, "confidence": 0.8, "synthetic": True}
ALERT = {"alert_id": "LA-1", "kind": "pair", "crimes": ["C1", "C2"], "score": 0.81, "band": "high",
         "factors": [{"factor": "mo_similarity", "weight": 0.3, "value": 0.9, "evidence": [], "reason": "x",
                      "struck_by_skeptic": False}], "status": "pending", "run_id": "run_1"}


def _s(**kw) -> Settings:
    return Settings(**{"_env_file": None, "supabase_url": "", "supabase_service_role_key": "", **kw})


# ----- selection (one pure function for runs and /health) ---------------------------------------------------

@pytest.mark.parametrize("kw, expected", [
    ({}, "local"),                                                              # live, no Supabase
    ({"sample_mode": True}, "memory"),                                          # judge fixtures stay byte-stable
    ({"supabase_url": "https://x", "supabase_service_role_key": "k"}, "supabase"),
    ({"supabase_url": "https://x", "supabase_service_role_key": "k", "sample_mode": True}, "supabase"),
    ({"nexus_store": "memory"}, "memory"),                                      # explicit wins
    ({"nexus_store": "local", "sample_mode": True}, "local"),
    ({"nexus_store": "LOCAL"}, "local"),
    ({"nexus_store": "supabase", "supabase_url": "https://x", "supabase_service_role_key": "k"}, "supabase"),
])
def test_store_kind_truth_table(kw, expected):
    assert store_kind(_s(**kw)) == expected


@pytest.mark.parametrize("kw", [{"nexus_store": "supabase"}, {"nexus_store": "redis"}])
def test_store_kind_fails_loudly(kw):
    with pytest.raises(ValueError):
        store_kind(_s(**kw))


def test_default_store_follows_the_selector(tmp_path):
    t = Tracer("r", tmp_path, echo=False)
    assert isinstance(default_store(_s(sample_mode=True), t), MemoryStore)
    local = default_store(_s(nexus_local_dir=str(tmp_path / "ls")), t)
    assert isinstance(local, LocalStore) and local.root == tmp_path / "ls"
    assert isinstance(default_store(_s(supabase_url="https://x", supabase_service_role_key="k"), t), SupabaseStore)


def test_env_var_selects_the_store(monkeypatch):
    monkeypatch.setenv("NEXUS_STORE", "memory")
    assert store_kind(Settings(_env_file=None)) == "memory"


# ----- contract, same assertions as the Memory/Supabase stores ------------------------------------------------

def test_series_grows_under_one_id_and_keeps_status(tmp_path):
    st = LocalStore(tmp_path)
    assert st.write_series(SER, "run_1") == "SER-NEW"
    grown = {"series_id": "SER-OTHERHASH", "crime_ids": ["C2", "C3", "C4"], "stations": []}
    assert st.write_series(grown, "run_2") == "SER-NEW"
    row = st.series()["SER-NEW"]
    assert row["crime_ids"] == ["C1", "C2", "C3", "C4"] and row["run_id"] == "run_2" and row["synthetic"] is True
    assert row["name"]


def test_d033_removes_only_named_members(tmp_path):
    st = LocalStore(tmp_path)
    st.write_series({"series_id": "S", "crime_ids": ["A", "B", "T", "X"]}, "run_1")
    sid = st.write_series({"series_id": "S2", "crime_ids": ["A", "B"]}, "run_2",
                          exclude=lambda others: {c: "test_fir" for c in others if c == "T"})
    assert sid == "S"
    assert st.series()["S"]["crime_ids"] == ["A", "B", "X"]  # T removed, X kept (not named)
    assert st.removed == [{"series_id": "S", "crime_id": "T", "reason": "test_fir"}]


def test_dossier_only_on_a_stored_series(tmp_path):
    """Like SupabaseStore (an unknown id updates nothing), not MemoryStore (which creates a row)."""
    st = LocalStore(tmp_path)
    assert st.write_dossier("SER-NOPE", {"text": "d"}) is False
    assert "SER-NOPE" not in st.series()
    st.write_series(SER, "run_1")
    assert st.write_dossier("SER-NEW", {"text": "d"}) is True
    st.write_series(SER, "run_2")
    assert st.series()["SER-NEW"]["dossier"] == {"text": "d"}  # a re-run never wipes the dossier


def test_alerts_with_factors_and_status_preserved(tmp_path):
    st = LocalStore(tmp_path)
    assert st.write_alert(ALERT) == ALERT
    data = json.loads((tmp_path / "link_alerts.json").read_text(encoding="utf-8"))
    assert data["LA-1"]["factors"][0]["factor"] == "mo_similarity"
    data["LA-1"]["status"] = "approved"  # as if an analyst decided it
    (tmp_path / "link_alerts.json").write_text(json.dumps(data), encoding="utf-8")
    st.write_alert({**ALERT, "score": 0.9})
    again = st.alerts()["LA-1"]
    assert again["score"] == 0.9 and again["status"] == "approved"  # agents never overwrite status


def test_runs_rows(tmp_path):
    st = LocalStore(tmp_path)
    st.start_run("run_1", "case", "logs/trace-run_1.jsonl", subject="C1")
    assert st.runs()["run_1"]["status"] == "running" and st.runs()["run_1"]["subject"] == "C1"
    st.finish_run("run_1", "success", "case")
    st.finish_run("run_2", "partial", "batch")
    assert st.runs()["run_1"]["status"] == "success" and st.runs()["run_1"]["finished"]
    assert st.runs()["run_2"]["status"] == "failed"  # same mapping as SupabaseStore


def test_notifications_stay_in_memory(tmp_path):
    st = LocalStore(tmp_path)
    st.notify([{"kind": "link_alert", "title": "t", "station_id": "PS-A"}])
    assert st.notifications and not (tmp_path / "notifications.json").exists()


# ----- what only a file store can do ------------------------------------------------------------------------

def test_round_trip_survives_a_restart(tmp_path):
    a = LocalStore(tmp_path)
    a.upsert_features(FEATS)
    a.write_alert(ALERT)
    a.write_series(SER, "run_1")
    b = LocalStore(tmp_path)  # a new process
    assert b.get_features("C1") == FEATS
    assert b.get_features("C9") is None
    assert b.alerts()["LA-1"]["band"] == "high"
    grown = {"series_id": "SER-HASH2", "crime_ids": ["C3", "C4", "C5"]}
    assert b.write_series(grown, "run_2") == "SER-NEW"  # id reuse across the restart


def test_memory_and_supabase_stores_never_answer_features(tmp_path):
    assert MemoryStore().get_features("C1") is None
    assert SupabaseStore(object(), Tracer("r", tmp_path, echo=False)).get_features("C1") is None


def test_writes_are_atomic_and_concurrent_writers_lose_nothing(tmp_path):
    def write(i):
        LocalStore(tmp_path).write_alert({**ALERT, "alert_id": f"LA-{i}"})

    threads = [threading.Thread(target=write, args=(i,)) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(LocalStore(tmp_path).alerts()) == 25
    assert not list(tmp_path.glob("*.tmp"))  # no temp files left behind


def _live_run(tmp_path, monkeypatch, options=None):
    """A live-mode /run with no Supabase: the selector picks LocalStore; Zetaris has no stored features."""
    from agents_fixtures import ADYAR, FakeNightshift, FakeZetaris, default_handlers
    from test_graph_pipeline import responder

    from app.graph import run_request
    monkeypatch.setattr(Settings, "logs_dir", property(lambda self: tmp_path / "logs"))
    handlers = default_handlers()
    handlers["q_features"] = lambda p: []
    ns = FakeNightshift(responder())
    s = _s(nexus_local_dir=str(tmp_path / "local"))
    out = run_request("case", {"crime_id": ADYAR["crime_id"]}, options or {}, s,
                      zetaris=FakeZetaris(handlers), nightshift=ns)
    mo_calls = sum(1 for _lane, _agent, purpose in ns.calls if purpose.startswith("mo "))
    events = [json.loads(x) for x in (tmp_path / "logs" / f"trace-{out['run_id']}.jsonl").read_text().splitlines()]
    return out, mo_calls, events, ADYAR["crime_id"]


def test_extractor_reuses_local_features_after_a_restart(tmp_path, monkeypatch):
    out1, calls1, _, cid = _live_run(tmp_path, monkeypatch)
    assert out1["status"] == "success" and calls1 >= 1
    local = LocalStore(tmp_path / "local")
    assert local.get_features(cid)["mo"] and local.alerts() and out1["run_id"] in local.runs()
    out2, calls2, events, _ = _live_run(tmp_path, monkeypatch)  # a fresh store instance reads the files
    assert calls2 == 0
    reused = [e for e in events if e["action"] == "features_reused"]
    assert reused and "local store" in (reused[0].get("output_summary") or "")
    assert LocalStore(tmp_path / "local").runs()[out2["run_id"]]["status"] == "success"


def test_force_extract_bypasses_local_features(tmp_path, monkeypatch):
    _live_run(tmp_path, monkeypatch)
    _, calls, _, _ = _live_run(tmp_path, monkeypatch, {"force_extract": True})
    assert calls >= 1


def test_empty_local_mo_is_not_reused(tmp_path, monkeypatch):
    from agents_fixtures import ADYAR
    LocalStore(tmp_path / "local").upsert_features({**FEATS, "crime_id": ADYAR["crime_id"],
                                                     "mo": {"approach": None, "target": ""}})
    _, calls, _, _ = _live_run(tmp_path, monkeypatch)
    assert calls >= 1


def test_directory_created_lazily(tmp_path):
    root = tmp_path / "not" / "yet"
    st = LocalStore(root)
    assert not root.exists() and st.get_features("C1") is None and st.series() == {}
    st.upsert_features(FEATS)
    assert (root / "crime_features.json").exists()
