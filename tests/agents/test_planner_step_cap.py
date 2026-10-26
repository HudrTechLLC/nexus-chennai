"""An optional Planner step gives up within STEP_TIMEOUT_S and the run carries on (chief, 2026-10-26).

Before: run_e97a1684 (CHN-VL-2026-001221, live) spent ~3 min on q_dq_flags under Zetaris load (60 s timeout x 3
attempts), the 300 s run deadline passed, and the case got no links and no alert. An optional step (anything but
q_candidates) now gets one attempt capped at STEP_TIMEOUT_S, is traced `step_degraded`, and is skipped for the rest
of the run (the adapter's fail-fast breaker). q_candidates keeps the normal timeout and retries: without it there is
nothing to score.
"""

import httpx
import pytest

from app.adapters.zetaris import ZetarisClient
from app.agents import AgentDeps, MemoryStore
from app.agents.planner import STEP_TIMEOUT_S, Plan, Planner, PlanStep
from app.config import Settings
from app.tracing import Tracer


class SlowDq:
    """Zetaris stand-in: the dq_flags view hangs, everything else answers at once."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sql = request.read().decode()
        self.calls.append((sql, request.extensions.get("timeout", {})))
        if "nexus.dq_flags" in sql:
            raise httpx.ReadTimeout("Zetaris busy", request=request)
        return httpx.Response(200, json={"data": []})

    def timeouts(self, marker: str) -> list[float | None]:
        return [t.get("read") for sql, t in self.calls if marker in sql]


@pytest.fixture
def run(tmp_path):
    fake = SlowDq()
    tracer = Tracer("t", tmp_path, echo=False)
    client = ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key="k"), tracer=tracer,
                           transport=httpx.MockTransport(fake))
    deps = AgentDeps(tracer=tracer, zetaris=client, store=MemoryStore(), nightshift=None)
    return fake, Planner(deps), tracer


def plan(round_no=1):
    return Plan(steps=[PlanStep("q_candidates", {"crime_id": "A", "days": 45, "ring": 6}),
                       PlanStep("q_dq_flags", {"ids": "A,B"}),
                       PlanStep("q_context", {"crime_id": "A"})], round=round_no, source="model")


def test_cap_is_about_thirty_seconds():
    assert 10 <= STEP_TIMEOUT_S <= 30


def test_a_hanging_optional_step_gives_up_once_is_traced_degraded_and_the_rest_runs(run):
    fake, planner, tracer = run
    out = planner.execute(plan())
    assert "q_dq_flags" not in out and {"q_candidates", "q_context"} <= set(out)
    assert fake.timeouts("nexus.dq_flags") == [STEP_TIMEOUT_S]  # one attempt, capped: no 60 s x 3
    ev = [e for e in tracer.read() if e["action"] in ("step_degraded", "step_failed")]
    assert [(e["action"], e["input_summary"], e["status"]) for e in ev] == [("step_degraded", "q_dq_flags", "degraded")]
    assert "run continues" in ev[0]["output_summary"]


def test_the_next_round_skips_it_without_calling_zetaris(run):
    fake, planner, tracer = run
    planner.execute(plan(1))
    planner.execute(plan(2))
    assert len(fake.timeouts("nexus.dq_flags")) == 1
    assert [e["status"] for e in tracer.read() if e["action"] == "step_degraded"] == ["degraded", "degraded"]


def test_q_candidates_is_not_capped(run):
    fake, planner, _ = run
    planner.execute(plan())
    cand = [t for sql, t in fake.calls if "nexus.dq_flags" not in sql][0]
    assert cand.get("read") != STEP_TIMEOUT_S  # the client's normal timeout, with retries


def test_a_timed_out_step_stays_skipped_for_the_whole_run_after_the_breaker_expires(run, monkeypatch):
    # run_3d845f76: round 2 came 3.7 min after round 1, the adapter's 60 s breaker had expired and q_dq_flags cost
    # another 30 s. The run remembers it: later rounds skip it without asking Zetaris.
    import app.adapters.zetaris as z

    monkeypatch.setattr(z, "BREAKER_SECONDS", 0.0)
    fake, planner, tracer = run
    planner.execute(plan(1))
    out = planner.execute(plan(2))
    assert "q_dq_flags" not in out and "q_context" in out
    assert len(fake.timeouts("nexus.dq_flags")) == 1
    ev = [e for e in tracer.read() if e["action"] == "step_degraded"]
    assert [e["status"] for e in ev] == ["degraded", "degraded"]
    assert "earlier in this run" in ev[1]["output_summary"]


def test_a_fresh_run_tries_the_step_again(tmp_path):
    # Remembered per run (on its deps), never across runs.
    fake = SlowDq()
    for i in range(2):
        tracer = Tracer(f"t{i}", tmp_path, echo=False)
        client = ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key="k"), tracer=tracer,
                               transport=httpx.MockTransport(fake))
        Planner(AgentDeps(tracer=tracer, zetaris=client, store=MemoryStore(), nightshift=None)).execute(plan())
    assert len(fake.timeouts("nexus.dq_flags")) == 2
