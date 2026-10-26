"""Embed lane (spec E2) and its TF-IDF + feature-vector fallback (D-027)."""

import subprocess
import sys
import time

import httpx
import pytest

from app.config import Settings
from app.engines import similarity as S
from app.engines import use_tracer
from app.tracing import Tracer


@pytest.fixture(autouse=True)
def _fresh_route():
    S.reset_route()
    yield
    S.reset_route()


@pytest.fixture
def tracer(tmp_path):
    t = Tracer("t", tmp_path, echo=False)
    with use_tracer(t):
        yield t


def settings(lane="nvidia/nemotron-3.5-embed-1b", **kw):
    return Settings(_env_file=None, sample_mode=False, meterless_runtime_token="tok", lane_embed=lane, **kw)


class Counting:
    def __init__(self, handler):
        self.calls = 0
        self.handler = handler

    def __call__(self, request):
        self.calls += 1
        return self.handler(request)


def test_unpinned_lane_makes_no_call_and_traces_one_fallback(tracer):
    fake = Counting(lambda r: httpx.Response(200))
    v = S.embed(["chain snatching near temple", "phone theft"], settings=settings(lane=""),
                transport=httpx.MockTransport(fake))
    assert fake.calls == 0 and v.source == "tfidf" and len(v.vectors) == 2
    (ev,) = tracer.read()
    assert ev["action"] == "embed_fallback" and ev["model"] is None and "not pinned" in ev["output_summary"]


def test_404_falls_back_once_and_remembers_the_route_is_down(tracer):
    fake = Counting(lambda r: httpx.Response(404, json={"message": "not_found"}))
    for _ in range(3):
        v = S.embed(["a b", "c d"], settings=settings(), transport=httpx.MockTransport(fake))
        assert v.source == "tfidf"
    assert fake.calls == 1  # one failed call, then remembered
    evs = tracer.read()
    assert [e["action"] for e in evs] == ["embed_fallback"] * 3
    assert "no embeddings route (HTTP 404)" in evs[0]["output_summary"]


def test_transport_timeout_falls_back_fast(tracer):
    def hang(request):
        raise httpx.ReadTimeout("wedged", request=request)
    fake = Counting(hang)
    t0 = time.perf_counter()
    v = S.embed(["x y"], settings=settings(), transport=httpx.MockTransport(fake))
    assert v.source == "tfidf" and fake.calls == 1 and time.perf_counter() - t0 < 10


def test_live_route_returns_model_vectors_with_model_and_receipt(tracer):
    def ok(request):
        assert request.url.path.endswith("/v1/embeddings")
        assert request.headers["meterless-scope"] == "user"
        body = request.read().decode()
        assert '"model":"nvidia/nemotron-3.5-embed-1b"' in body.replace(" ", "")
        return httpx.Response(200, headers={"meterless-receipt": "rc-9"}, json={
            "model": "nvidia/nemotron-3.5-embed-1b",
            "data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]})
    v = S.embed(["first", "second"], settings=settings(), transport=httpx.MockTransport(ok))
    assert v.source == "nightshift" and v.vectors == [[1.0, 0.0], [0.0, 1.0]] and v.receipt_id == "rc-9"
    (ev,) = tracer.read()
    assert ev["action"] == "embed" and ev["model"] == "nvidia/nemotron-3.5-embed-1b" and ev["receipt_id"] == "rc-9"


def test_short_live_response_falls_back_for_the_whole_batch(tracer):
    bad = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}))
    v = S.embed(["a", "b"], settings=settings(), transport=bad)
    assert v.source == "tfidf" and all(isinstance(x, dict) for x in v.vectors)


def test_sparse_and_dense_vectors_never_mix():
    with pytest.raises(TypeError):
        S.cosine({"a": 1.0}, [1.0])


MO_A = {"mo": {"approach": "two men on motorcycle", "target": "woman walking", "target_item": "gold chain",
               "escape": "motorcycle"}, "visual_tags": ["red_bike", "helmet"]}
MO_B = {"mo": {"approach": "two men on a motorcycle", "target": "elderly woman", "target_item": "gold chain",
               "escape": "motorcycle"}, "visual_tags": ["red_bike"]}
MO_C = {"mo": {"approach": "broke window", "target": "parked car", "target_item": "laptop", "escape": "on foot"},
        "visual_tags": ["glass"]}


def test_mo_cosine_ranks_near_identical_mo_above_unrelated():
    assert S.mo_cosine(MO_A, MO_B) > 0.6 > 0.05 > S.mo_cosine(MO_A, MO_C)
    assert S.mo_cosine(MO_A, MO_B) == S.mo_cosine(MO_B, MO_A)
    assert S.mo_cosine(MO_A, None) is None


def test_mo_vector_is_field_tagged_and_independent_of_other_records():
    v = S.mo_vector(MO_A)
    assert "target_item=gold" in v and "tag=red" in v and "gold" not in v
    assert S.mo_vector(MO_A) == v  # no corpus state


def test_rank_puts_the_matching_document_first(tracer):
    docs = ["Phone stolen from a parked car", "Gold chain snatched by two men on a red motorcycle",
            "House break-in at night"]
    order = S.rank("chain snatching motorcycle", docs, settings=settings(lane=""))
    assert order[0][0] == 1 and order[0][1] > order[1][1]


def test_vectors_are_identical_across_processes():
    code = ("from app.engines import similarity as S; from app.config import Settings; "
            "v=S.embed(['gold chain snatched','phone theft at bus stop'], settings=Settings(_env_file=None, "
            "lane_embed='')); print(sorted(v.vectors[0].items()))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           cwd="services/api").stdout for _ in range(2)}
    assert len(outs) == 1
