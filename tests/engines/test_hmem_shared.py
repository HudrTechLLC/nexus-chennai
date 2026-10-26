"""H-MEM shared across processes: the worker records a decision, the API's next adjust() sees it, no restart.

Process A is a real subprocess (as the worker is); process B is this test process, opened before A wrote.
Runs once per backend (conftest): sample, and the TypeScript sidecar when it is up.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from app.engines import hmem

from .conftest import CLOCK
from .test_hmem import REJECTED, SIMILAR_TO_REJECTED, RED_PULSAR

API_DIR = Path(__file__).resolve().parents[2] / "services" / "api"

WRITER = """
import json, sys
from app.engines import hmem
hmem.configure(sys.argv[1], clock=lambda: 1_790_000_000_000)
for alert_id, decision, pair in json.loads(sys.argv[2]):
    hmem.record_decision(alert_id, decision, "different_offenders" if decision == "reject" else None, None, pair)
"""


def _writer(mem_dir, decisions) -> subprocess.Popen:
    env = {**os.environ, "ENGINES_SIDECAR_NS": f"writer-{uuid.uuid4().hex}"}  # its own sidecar session
    env.pop("ENGINES_PERSIST", None)
    return subprocess.Popen([sys.executable, "-c", WRITER, str(mem_dir), json.dumps(decisions)], cwd=API_DIR,
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _run(proc: subprocess.Popen) -> None:
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 0, err[-2000:]


def test_a_decision_written_by_another_process_shapes_the_next_score(tmp_path):
    mem_dir = tmp_path / "shared"
    hmem.configure(mem_dir, clock=CLOCK)          # the API: opened before anything was decided
    assert hmem.adjust(SIMILAR_TO_REJECTED)["delta"] == 0.0

    _run(_writer(mem_dir, [["LA-201", "reject", REJECTED]]))   # the worker records the analyst's reject

    adj = hmem.adjust(SIMILAR_TO_REJECTED)                    # same API instance, no restart
    assert adj["delta"] < 0 and adj["memory_ids"], adj
    assert "rejected (different_offenders)" in adj["reason"]


def test_concurrent_writers_lose_no_decision(tmp_path):
    mem_dir = tmp_path / "shared"
    hmem.configure(mem_dir, clock=CLOCK)
    a = _writer(mem_dir, [[f"LA-A{i}", "reject", REJECTED] for i in range(4)])
    b = _writer(mem_dir, [[f"LA-B{i}", "approve", RED_PULSAR] for i in range(4)])
    _run(a)
    _run(b)
    alerts = {t for r in hmem.instance().records() for t in r["tags"] if t.startswith("alert:")}
    assert alerts == {f"alert:LA-A{i}" for i in range(4)} | {f"alert:LA-B{i}" for i in range(4)}
    assert not (mem_dir / ".write.lock").exists()


READER = """
import json, sys
from app.engines import hmem
hmem.configure(sys.argv[1], clock=lambda: 1_790_000_000_000)
pair = json.loads(sys.argv[2])
for _ in range(int(sys.argv[3])):
    hmem.adjust(pair)        # retrieval writes "read" ledger entries and state.json
"""


def test_scoring_while_the_worker_records_loses_no_decision(tmp_path):
    """adjust() is not read-only (H-MEM logs reads), so an API scoring pairs must not overwrite a decision the
    worker records at the same moment."""
    mem_dir = tmp_path / "shared"
    hmem.configure(mem_dir, clock=CLOCK)
    env = {**os.environ, "ENGINES_SIDECAR_NS": f"reader-{uuid.uuid4().hex}"}
    env.pop("ENGINES_PERSIST", None)
    reader = subprocess.Popen([sys.executable, "-c", READER, str(mem_dir), json.dumps(SIMILAR_TO_REJECTED), "40"],
                              cwd=API_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    writer = _writer(mem_dir, [[f"LA-W{i}", "reject", REJECTED] for i in range(6)])
    _run(writer)
    _run(reader)
    alerts = {t for r in hmem.instance().records() for t in r["tags"] if t.startswith("alert:")}
    assert alerts == {f"alert:LA-W{i}" for i in range(6)}
    assert hmem.adjust(SIMILAR_TO_REJECTED)["delta"] < 0
