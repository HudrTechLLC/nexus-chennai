"""Series persistence (series + series_members + dossier), runs.subject and new-case pickup."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from test_worker_store import FakeSB, worker  # noqa: E402

from app.agents import MemoryStore  # noqa: E402
from app.agents.base import choose_series_id  # noqa: E402
from app.graph.store import SupabaseStore  # noqa: E402
from app.tracing import Tracer  # noqa: E402

SER = {"series_id": "SER-NEW", "crime_ids": ["C1", "C2", "C3"], "stations": ["PS-A", "PS-B"]}


def test_choose_series_id_reuses_largest_overlap():
    assert choose_series_id(SER, {}) == "SER-NEW"
    assert choose_series_id(SER, {"C1": "SER-B", "C2": "SER-A", "C3": "SER-A"}) == "SER-A"
    assert choose_series_id(SER, {"C1": "SER-B", "C2": "SER-A"}) == "SER-A"  # tie -> smaller id


def test_memory_store_series_grows_under_one_id():
    st = MemoryStore()
    assert st.write_series(SER, "run_1") == "SER-NEW"
    grown = {"series_id": "SER-OTHERHASH", "crime_ids": ["C2", "C3", "C4"], "stations": []}
    assert st.write_series(grown, "run_2") == "SER-NEW"
    assert st.series["SER-NEW"]["crime_ids"] == ["C1", "C2", "C3", "C4"]


def test_supabase_store_series_rows_keep_analyst_status(tmp_path):
    sb = FakeSB({"series": [{"series_id": "SER-OLD", "name": "x", "status": "confirmed", "dossier": {"text": "d"}}],
                 "series_members": [{"series_id": "SER-OLD", "crime_id": "C1"}, {"series_id": "SER-OLD", "crime_id": "C2"}]})
    store = SupabaseStore(sb, Tracer("r", tmp_path, echo=False))
    sid = store.write_series(SER, "run_9")
    assert sid == "SER-OLD"
    row = sb.tables["series"][0]
    assert row["status"] == "confirmed" and row["dossier"] == {"text": "d"}  # never overwritten
    assert row["run_id"] == "run_9" and row["synthetic"] is True and row["name"].startswith("3 linked cases")
    assert sorted(m["crime_id"] for m in sb.tables["series_members"]) == ["C1", "C2", "C3"]
    store.write_dossier("SER-OLD", {"text": "new"})
    assert sb.tables["series"][0]["dossier"] == {"text": "new"}


def test_start_run_subject_falls_back_before_migration(tmp_path):
    class NoSubjectSB(FakeSB):
        def upsert(self, table, rows, on_conflict):
            if table == "runs" and "subject" in (rows if isinstance(rows, dict) else rows[0]):
                raise RuntimeError('column "subject" of relation "runs" does not exist')
            return super().upsert(table, rows, on_conflict)

    sb = NoSubjectSB()
    SupabaseStore(sb, Tracer("r", tmp_path, echo=False)).start_run("run_1", "case", "logs/x", subject="C1")
    assert sb.tables["runs"][0]["run_id"] == "run_1" and "subject" not in sb.tables["runs"][0]
    ok = FakeSB()
    SupabaseStore(ok, Tracer("r", tmp_path, echo=False)).start_run("run_2", "case", "logs/x", subject="C1")
    assert ok.tables["runs"][0]["subject"] == "C1"


def test_new_case_pickup_ignores_future_reported_at(tmp_path):
    sb = FakeSB({"crimes": [{"crime_id": "C1"}], "crime_features": []})
    worker(tmp_path, sb).process_new_cases()
    params = next(p for op, t, p in sb.log if op == "select" and t == "crimes")
    assert params["reported_at"].startswith("lte.") and params["order"] == "reported_at.desc"


def test_worker_writes_missing_dossiers(tmp_path):
    from agents_fixtures import ADYAR, VELACHERY
    sb = FakeSB({"series": [{"series_id": "SER-1", "dossier": None, "created_at": "2026-10-26"},
                            {"series_id": "SER-2", "dossier": {"text": "done"}, "created_at": "2026-10-25"}],
                 "series_members": [{"series_id": "SER-1", "crime_id": ADYAR["crime_id"]},
                                    {"series_id": "SER-1", "crime_id": VELACHERY["crime_id"]}]})
    w = worker(tmp_path, sb)
    assert w.process_dossiers() == 1
    d = sb.tables["series"][0]["dossier"]
    assert d["text"] and d["cited_ids"] and d["run_id"] == "w" and d["generated_at"]
    assert d["model"] is None  # the test model never wrote a valid chunk: extractive fallback, said so
    assert sb.tables["series"][1]["dossier"] == {"text": "done"}
    assert w.process_dossiers() == 0


def test_new_case_pickup_can_be_limited_to_recent_filings(tmp_path):
    sb = FakeSB({"crimes": [{"crime_id": "C1"}], "crime_features": []})
    w = worker(tmp_path, sb)
    w.new_cases_since = "2026-10-26T15:00:00+05:30"
    w.process_new_cases()
    params = next(p for op, t, p in sb.log if op == "select" and t == "crimes")
    assert params["created_at"] == "gt.2026-10-26T15:00:00+05:30"
