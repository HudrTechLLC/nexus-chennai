"""Trace copy to Supabase with redaction, and the system_status heartbeat (WS3-08, D-025)."""

from __future__ import annotations

from test_worker_store import FakeSB, worker

from app.graph.redact import redact_event
from app.graph.store import SupabaseStore
from app.tracing import Tracer

SECRET_LINES = [
    "token=abcd1234efgh5678",
    "Authorization: Bearer abcdef0123456789abcdef",
    "key nvapi-AbCdEf0123456789xyz",
    "service sb_secret_AbCdEf012345",
    "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
    "passphrase: correct horse battery staple",
    "hash argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
]


def test_planted_secrets_never_reach_the_row(tmp_path):
    tr = Tracer("run_sec", tmp_path, echo=False)
    for line in SECRET_LINES:
        tr.emit("Planner", "plan", input_summary=line, output_summary=f"echo {line}", status="ok")
    sb = FakeSB()
    SupabaseStore(sb, tr).finish_run("run_sec", "success")
    stored = " ".join(str(r) for r in sb.tables["trace_events"])
    for secret in ("abcd1234efgh5678", "abcdef0123456789abcdef", "nvapi-AbCdEf", "sb_secret_AbCd",
                   "eyJhbGciOiJIUzI1NiJ9", "horse battery", "argon2id$"):
        assert secret not in stored, secret
    assert "[redacted]" in stored
    # The JSONL on disk is untouched (R3).
    assert any("abcd1234efgh5678" in str(e) for e in tr.read())


def test_tip_text_is_cut_and_ids_are_kept():
    e = redact_event({"agent_name": "Tip Guard", "action": "screen_tip",
                      "input_summary": "TIP-8F3K2Q " + "same red bike parks near the tea shop every evening " * 5,
                      "output_summary": "verdict clean", "zetaris_query_ids": ["3f2c9a10-1b2c-4d5e-8f90-123456789abc"]})
    assert len(e["input_summary"]) <= 60 and e["input_summary"].startswith("TIP-8F3K2Q")
    assert e["zetaris_query_ids"] == ["3f2c9a10-1b2c-4d5e-8f90-123456789abc"]
    q = redact_event({"agent_name": "Skeptic", "action": "strike_factor",
                      "output_summary": "query 3f2c9a10-1b2c-4d5e-8f90-123456789abc; score 0.86→0.82"})
    assert "3f2c9a10-1b2c-4d5e-8f90-123456789abc" in q["output_summary"]


def test_run_row_is_written_before_trace_rows(tmp_path):
    tr = Tracer("run_ord", tmp_path, echo=False)
    for i in range(3):
        tr.emit("Linker", "score_pair", input_summary=f"p{i}", zetaris_query_ids=[f"q{i}"], confidence=0.8)
    sb = FakeSB()
    SupabaseStore(sb, tr).finish_run("run_ord", "deadline", kind="batch")
    ops = [(op, t) for op, t, _ in sb.log]
    assert ops.index(("upsert", "runs")) < ops.index(("upsert", "trace_events"))
    run = sb.tables["runs"][0]
    assert run["status"] == "failed" and run["kind"] == "batch" and run["log_path"] == "logs/trace-run_ord.jsonl"
    rows = sb.tables["trace_events"]
    assert [r["seq"] for r in rows] == [0, 1, 2] and rows[2]["zetaris_query_ids"] == ["q2"]
    assert rows[0]["confidence"] == 0.8 and rows[0]["agent_name"] == "Linker"


def test_trace_copy_failure_does_not_lose_the_run(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
    from agents_fixtures import ADYAR, FakeNightshift, FakeZetaris, default_handlers

    from app.config import Settings
    from app.graph import run_request

    class Broken(FakeSB):
        def upsert(self, table, rows, on_conflict):
            if table == "trace_events":
                raise RuntimeError("supabase down")
            return super().upsert(table, rows, on_conflict)

    monkeypatch.setattr(Settings, "logs_dir", property(lambda self: tmp_path / "logs"))
    out = run_request("case", {"crime_id": ADYAR["crime_id"]}, {}, Settings(_env_file=None),
                      store_factory=lambda s, t: SupabaseStore(Broken(), t),
                      zetaris=FakeZetaris(default_handlers()), nightshift=FakeNightshift(lambda *a: "{}"))
    assert out["status"] == "success" and out["output"]["alerts"]


def test_heartbeat_writes_status_rows(tmp_path):
    sb = FakeSB()
    w = worker(tmp_path, sb)
    assert w.heartbeat() > 0
    comps = {r["component"]: r["state"] for r in sb.tables["system_status"]}
    assert comps["zetaris"] == "down" and comps["engines"] == "live" and comps["worker"] == "live"


def test_heartbeat_never_fails_a_worker_pass(tmp_path):
    class Broken(FakeSB):
        def upsert(self, table, rows, on_conflict):
            raise RuntimeError("supabase down")

    w = worker(tmp_path, Broken())
    assert w.run_once() == {"decisions": 0, "tips": 0, "cases": 0}
    assert any(e["action"] == "heartbeat_failed" for e in w.tracer.read())
