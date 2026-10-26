"""The trace echo never fails a step (live: a Windows worker logging to a file crashed a dossier on '→')."""

import io
import json
import sys

from app.tracing import Tracer


def test_echo_to_a_cp1252_stream_never_raises(tmp_path, monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", errors="strict"))
    monkeypatch.delenv("NEXUS_TRACE_STREAM", raising=False)
    t = Tracer("r", tmp_path, echo=True)
    t.emit("Skeptic", "strike_factor", output_summary="score 0.79→0.61 · Velachery")
    sys.stdout.flush()
    assert t.read()[0]["output_summary"] == "score 0.79→0.61 · Velachery"  # the record is exact
    echoed = raw.getvalue().decode("cp1252")
    assert json.loads(echoed)["output_summary"] == "score 0.79→0.61 · Velachery"  # escaped, still valid JSON


def test_echo_to_a_closed_stream_never_raises(tmp_path, monkeypatch):
    s = io.StringIO()
    s.close()
    monkeypatch.setattr(sys, "stdout", s)
    monkeypatch.delenv("NEXUS_TRACE_STREAM", raising=False)
    t = Tracer("r", tmp_path, echo=True)
    t.emit("Worker", "heartbeat")
    assert t.read()[0]["action"] == "heartbeat"
