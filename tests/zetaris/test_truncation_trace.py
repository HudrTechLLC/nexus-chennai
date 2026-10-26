"""D-031: a result that fills the limit is flagged in the trace (zetaris_result_truncated), never silent."""

import json

from app.adapters.zetaris import NamedQuery, ZetarisClient
from app.config import Settings
from app.tracing import Tracer

Q = NamedQuery("q_three", "SELECT 1", "SELECT * FROM range(3) t(n)", "three rows", ("n",))


def _events(tracer):
    return [json.loads(x) for x in tracer.path.read_text(encoding="utf-8").splitlines()]


def _client(tmp_path):
    tracer = Tracer("t", tmp_path, echo=False)
    return ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""), tracer=tracer,
                         registry={Q.name: Q}), tracer


def test_full_page_emits_truncated_event(tmp_path):
    c, tracer = _client(tmp_path)
    assert len(c.named("q_three", agent="T", limit=2).rows) == 2
    ev = [e for e in _events(tracer) if e["action"] == "zetaris_result_truncated"]
    assert len(ev) == 1 and "limit=2" in ev[0]["output_summary"] and ev[0]["input_summary"] == "q_three"


def test_complete_answer_emits_no_truncated_event(tmp_path):
    c, tracer = _client(tmp_path)
    assert len(c.named("q_three", agent="T", limit=10).rows) == 3
    assert not [e for e in _events(tracer) if e["action"] == "zetaris_result_truncated"]
