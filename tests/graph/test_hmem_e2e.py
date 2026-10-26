"""LNK-08 end to end across the two processes' code paths: a decision the worker records changes the next
/run on a similar pair, and the alert row written to Supabase carries memory_applied (memory id + effect)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from agents_fixtures import ADYAR, FakeNightshift, FakeZetaris, default_handlers  # noqa: E402
from test_graph_pipeline import responder  # noqa: E402
from test_worker_store import FakeSB, worker  # noqa: E402

from app import engines  # noqa: E402
from app.config import Settings  # noqa: E402
from app.graph import run_request  # noqa: E402
from app.graph.store import SupabaseStore  # noqa: E402


def _run(tmp_path, sb, run_id):
    s = Settings(_env_file=None, sample_mode=True)
    return run_request("case", {"crime_id": ADYAR["crime_id"]}, {}, s, run_id=run_id,
                       zetaris=FakeZetaris(default_handlers()), nightshift=FakeNightshift(responder()),
                       store_factory=lambda settings, tracer: SupabaseStore(sb, tracer))


def test_worker_decision_reaches_next_run_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "logs_dir", property(lambda self: tmp_path / "logs"))
    engines.hmem.configure(persist_dir=tmp_path / "hmem")

    sb = FakeSB()
    first = _run(tmp_path, sb, "run-before")
    before = next(a for a in sb.tables["link_alerts"] if a["run_id"] == "run-before")
    assert not before["memory_applied"]  # no memory yet

    # the analyst rejects that link in the console; the worker turns it into an H-MEM memory
    sb.tables["alert_decisions"] = [{"decision_id": 1, "alert_id": before["alert_id"], "decision": "reject",
                                     "reason_code": "different_offenders", "note": "different riders",
                                     "processed_at": None}]
    assert worker(tmp_path, sb).process_decisions() == 1

    _run(tmp_path, sb, "run-after")
    after = next(a for a in sb.tables["link_alerts"] if a["alert_id"] == before["alert_id"])
    assert after["run_id"] == "run-after"
    mem = after["memory_applied"]
    assert mem and all(m["memory_id"] and m["memory_id"] != "HM-unknown" and float(m["effect"]) < 0 for m in mem), mem
    assert after["score"] < first["output"]["alerts"][0]["score"]
    assert after["status"] == "rejected"  # the re-run never overwrites the analyst's decision
