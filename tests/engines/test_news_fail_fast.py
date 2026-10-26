"""q_news fails fast (chief, 2026-10-26): live, Zetaris reads the news REST table from this API, so a q_news
call is a callback into us. One attempt with an 8 s timeout, then skipped for the run; callers degrade to
"no news" with a trace line and never fail the run."""

import httpx
import pytest

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient, ZetarisError
from app.adapters.zetaris_queries_n2 import NEWS_TIMEOUT_S
from app.agents.base import AgentDeps
from app.agents.linker import Linker
from app.agents.planner import Plan, Planner, PlanStep
from app.config import Settings
from app.tracing import Tracer


class Hanging:
    """Zetaris stand-in: q_news times out, everything else answers."""

    def __init__(self):
        self.calls: list[str] = []
        self.timeouts: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sql = request.read().decode()
        self.calls.append(sql)
        self.timeouts.append(request.extensions.get("timeout", {}))
        if "v_news_mentions" in sql:
            raise httpx.ReadTimeout("feed callback hung", request=request)
        if "SELECT 1" in sql:
            return httpx.Response(200, json={"data": [[1]]})
        return httpx.Response(200, json={"data": []})

    def news_calls(self) -> int:
        return sum("v_news_mentions" in c for c in self.calls)


@pytest.fixture
def live(tmp_path):
    fake = Hanging()
    tracer = Tracer("t", tmp_path, echo=False)
    client = ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key="k"), tracer=tracer,
                           transport=httpx.MockTransport(fake))
    return fake, client, tracer


def test_q_news_is_declared_fail_fast_under_ten_seconds():
    assert NAMED_QUERIES["q_news"].timeout_s == NEWS_TIMEOUT_S <= 10


def test_one_attempt_with_the_short_timeout_then_skipped_for_the_run(live):
    fake, client, tracer = live
    with pytest.raises(ZetarisError):
        client.named("q_news", agent="Linker", crime_id="A")
    assert fake.news_calls() == 1  # no retries
    assert fake.timeouts[0].get("read") == NEWS_TIMEOUT_S
    with pytest.raises(ZetarisError, match="skipped"):
        client.named("q_news", agent="Linker", crime_id="B")
    assert fake.news_calls() == 1  # breaker: Zetaris not called again
    errors = [e for e in tracer.read() if e.get("status") == "error"]
    assert len(errors) == 2 and all(e["input_summary"] == "q_news" for e in errors)
    # Other queries are unaffected: still answered, with the client's normal timeout.
    assert client.named("q_ping", agent="t").rows == [[1]]
    assert fake.timeouts[-1].get("read") != NEWS_TIMEOUT_S


def test_planner_degrades_to_no_news(live):
    fake, client, tracer = live
    deps = AgentDeps(tracer=tracer, zetaris=client, nightshift=None)
    out = Planner(deps).execute(Plan(steps=[PlanStep("q_news", {"crime_id": "A"}),
                                            PlanStep("q_ping", {})], round=1, source="default"))
    assert "q_news" not in out and out["q_ping"]["rows"] == [{"one": 1}]
    assert any(e["action"] == "step_failed" and e["input_summary"] == "q_news" for e in tracer.read())


def test_linker_support_degrades_to_no_news_and_stops_asking(live):
    fake, client, tracer = live
    linker = Linker(AgentDeps(tracer=tracer, zetaris=client, nightshift=None))
    for cid in ("B1", "B2", "B3"):
        rows, _, _ = linker._candidate_support({"crime_id": cid, "location": {}}, None)
        assert "q_news" not in rows
    assert fake.news_calls() == 1  # three candidates, one hung call
    assert sum(e["action"] == "support_failed" for e in tracer.read()) >= 3
