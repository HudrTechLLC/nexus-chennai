"""Similarity vectors for similar-MO and text search (spec E2 `embed` lane). Owner: nexus-2.

Spec E2: `embed` = a Nemotron embedding model, with the fallback "TF-IDF + feature vectors in code (no model
call)". Nightshift 1.2.7 exposes no embeddings route: POST /v1/embeddings returns 404 for every listed embed
model, because those models are internal enrichment lanes (DECISIONS D-027). So today every call takes the
fallback, and the trace says so (`embed_fallback`, model null, with the reason). If a later Nightshift serves
/v1/embeddings, the live path turns on with no code change: LANE_EMBED pins the model.

Three entry points:
- `embed(texts)`: vectors for a batch. The whole batch is live or the whole batch is TF-IDF, never mixed,
  and the result says which (`source`), so callers never compare a dense model vector with a sparse one.
  The live call is one attempt with an 8 s timeout and no retries. After a 404 or a transport error the
  route is marked down for ROUTE_DOWN_SECONDS, so a run pays for at most one failed call.
- `mo_vector` / `mo_cosine`: field-tagged MO feature vectors for pair scoring. They use no IDF, so a pair's
  score depends only on the two records, not on which other candidates a run fetched.
- `rank(query, docs)`: text search. IDF is computed over the returned rows (per query is fine for ranking).

Everything is deterministic: no hash(), sorted tokens, rounded weights.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from app.engines._runtime import get_tracer

AGENT = "Similarity"
LANE = "embed"
EMBED_TIMEOUT_S = 8.0
ROUTE_DOWN_SECONDS = 600.0
ROUND = 6

# MO fields and their weight inside a feature vector (mirrors scoring.factors.MO_FIELD_WEIGHTS; kept here so
# the engines package does not import scoring).
MO_FIELD_WEIGHTS: Mapping[str, float] = {
    "approach": 3.0, "target": 2.0, "target_item": 2.0, "offender_count": 1.5, "escape": 1.5,
    "violence": 1.0, "time_band": 1.0, "place_type": 1.0, "disguise": 1.0, "verbal": 0.5,
}
TAG_WEIGHT = 1.0

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at by for from in into is of on or the to was were with near".split())

_route_down_until = 0.0
_route_lock = threading.Lock()


@dataclass(frozen=True)
class Vectors:
    source: str                      # "nightshift" or "tfidf"
    vectors: list[Any]               # dense list[float] (nightshift) or sparse dict[str, float] (tfidf)
    model: str | None = None
    receipt_id: str | None = None
    reason: str | None = None        # why the fallback was used


# ---------------------------------------------------------------------------- tokens and vectors

def tokens(text: Any) -> list[str]:
    if text is None:
        return []
    if isinstance(text, (list, tuple, set)):
        return [t for item in text for t in tokens(item)]
    return [t for t in _TOKEN.findall(str(text).lower()) if t not in _STOP and len(t) > 1]


def _normalise(vec: Mapping[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if not norm:
        return {}
    return {k: round(v / norm, ROUND) for k, v in sorted(vec.items()) if v}


def tfidf(docs: Sequence[Sequence[str]], idf: Mapping[str, float] | None = None) -> list[dict[str, float]]:
    """Sublinear TF x smoothed IDF, L2-normalised. IDF comes from `docs` unless one is given."""
    if idf is None:
        n = len(docs)
        df = Counter(t for d in docs for t in set(d))
        idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
    default = max(idf.values(), default=1.0)
    out = []
    for d in docs:
        tf = Counter(d)
        out.append(_normalise({t: (1.0 + math.log(c)) * idf.get(t, default) for t, c in tf.items()}))
    return out


def cosine(u: Any, v: Any) -> float | None:
    """Cosine of two vectors of the same kind (both sparse dicts or both dense lists)."""
    if not u or not v:
        return None
    if isinstance(u, dict) != isinstance(v, dict):
        raise TypeError("cannot compare a sparse TF-IDF vector with a dense model vector")
    if isinstance(u, dict):
        dot = sum(u[k] * v[k] for k in u.keys() & v.keys())
        nu, nv = math.sqrt(sum(x * x for x in u.values())), math.sqrt(sum(x * x for x in v.values()))
    else:
        if len(u) != len(v):
            raise ValueError("vectors differ in dimension")
        dot = sum(a * b for a, b in zip(u, v))
        nu, nv = math.sqrt(sum(a * a for a in u)), math.sqrt(sum(b * b for b in v))
    return round(dot / (nu * nv), 4) if nu and nv else None


def mo_vector(features: Mapping[str, Any] | None) -> dict[str, float]:
    """Field-tagged MO feature vector: `approach=snatch`, `tag=red_bike`, ... weighted by field. No IDF."""
    if not features:
        return {}
    mo = features.get("mo") or {}
    vec: dict[str, float] = {}
    for field, w in MO_FIELD_WEIGHTS.items():
        for tok in tokens(mo.get(field)):
            key = f"{field}={tok}"
            vec[key] = vec.get(key, 0.0) + w
    for tok in tokens(features.get("visual_tags")):
        key = f"tag={tok}"
        vec[key] = vec.get(key, 0.0) + TAG_WEIGHT
    return _normalise(vec)


def mo_cosine(features_a: Mapping[str, Any] | None, features_b: Mapping[str, Any] | None) -> float | None:
    """Similarity of two MO records from their feature vectors (stable per pair)."""
    return cosine(mo_vector(features_a), mo_vector(features_b))


# ---------------------------------------------------------------------------- embed lane

def _route_is_down() -> bool:
    return time.monotonic() < _route_down_until


def _mark_route_down() -> None:
    global _route_down_until
    with _route_lock:
        _route_down_until = time.monotonic() + ROUTE_DOWN_SECONDS


def reset_route() -> None:
    """Forget a remembered route failure (tests, or after a Nightshift upgrade)."""
    global _route_down_until
    with _route_lock:
        _route_down_until = 0.0


def _settings():
    from app.config import get_settings

    return get_settings()


def _live(texts: list[str], model: str, settings: Any, transport: httpx.BaseTransport | None) -> Vectors:
    headers = {
        "Authorization": f"Bearer {settings.meterless_runtime_token}",
        "meterless-app": settings.meterless_app,
        "meterless-scope": "user",
    }
    with httpx.Client(base_url=settings.meterless_base_url.rstrip("/"), timeout=EMBED_TIMEOUT_S,
                      transport=transport, trust_env=False) as client:
        resp = client.post("/embeddings", json={"model": model, "input": texts}, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    rows = sorted(data.get("data") or [], key=lambda r: r.get("index", 0))
    vectors = [r.get("embedding") for r in rows]
    if len(vectors) != len(texts) or not all(isinstance(v, list) and v for v in vectors):
        raise ValueError(f"embeddings response has {len(vectors)} vectors for {len(texts)} texts")
    receipt = next((v for k, v in resp.headers.items() if k.lower().startswith(("meterless-receipt",
                                                                                "x-meterless-receipt"))),
                   data.get("receipt_id") or data.get("id"))
    return Vectors("nightshift", vectors, model=data.get("model") or model, receipt_id=receipt)


def embed(texts: Sequence[str], *, purpose: str = "", settings: Any = None, idf: Mapping[str, float] | None = None,
          transport: httpx.BaseTransport | None = None) -> Vectors:
    """Vectors for a batch of texts: the embed lane when Nightshift serves it, else TF-IDF in code."""
    texts = [str(t or "") for t in texts]
    s = settings or _settings()
    model = (s.lanes or {}).get(LANE)
    reason = None
    if not texts:
        reason = "empty batch"
    elif not model:
        reason = "embed lane not pinned (LANE_EMBED)"
    elif s.sample_mode and not s.meterless_runtime_token:
        reason = "sample mode without a Nightshift token"
    elif _route_is_down():
        reason = f"embeddings route failed within the last {int(ROUTE_DOWN_SECONDS)} s"
    else:
        started = time.perf_counter()
        try:
            out = _live(texts, model, s, transport)
        except (httpx.HTTPError, ValueError) as exc:
            _mark_route_down()
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            reason = (f"Nightshift has no embeddings route (HTTP {code})" if code == 404
                      else f"embeddings call failed: {type(exc).__name__}: {str(exc)[:120]}")
        else:
            ms = int((time.perf_counter() - started) * 1000)
            get_tracer().emit(AGENT, "embed", input_summary=f"lane={LANE} {purpose} n={len(texts)}".strip(),
                              output_summary=f"{len(out.vectors)} vectors dim={len(out.vectors[0])} ms={ms}",
                              model=model, routed_model=out.model, receipt_id=out.receipt_id, status="ok")
            return out
    vecs = tfidf([tokens(t) for t in texts], idf)
    get_tracer().emit(AGENT, "embed_fallback", input_summary=f"lane={LANE} {purpose} n={len(texts)}".strip(),
                      output_summary=f"TF-IDF in code: {reason}", model=None, status="fallback")
    return Vectors("tfidf", vecs, reason=reason)


def rank(query: str, docs: Sequence[str], *, purpose: str = "search", settings: Any = None,
         transport: httpx.BaseTransport | None = None) -> list[tuple[int, float]]:
    """(index, score) of `docs` by similarity to `query`, best first; ties keep input order."""
    if not docs:
        return []
    v = embed([query, *docs], purpose=purpose, settings=settings, transport=transport)
    q, rest = v.vectors[0], v.vectors[1:]
    scored = [(i, cosine(q, d) or 0.0) for i, d in enumerate(rest)]
    return sorted(scored, key=lambda x: (-x[1], x[0]))


def rank_rows(query: str | None, rows: Sequence[Mapping[str, Any]], *, text_key: str = "text",
              purpose: str = "search", settings: Any = None,
              transport: httpx.BaseTransport | None = None) -> list[dict[str, Any]]:
    """Search rows re-ranked by text relevance to `query`; each row gains a `score`.

    With no query (a filters-only search) the rows keep their order and score is None."""
    rows = [dict(r) for r in rows]
    if not (query or "").strip() or not rows:
        return [{**r, "score": None} for r in rows]
    order = rank(query or "", [str(r.get(text_key) or "") for r in rows], purpose=purpose, settings=settings,
                 transport=transport)
    return [{**rows[i], "score": s} for i, s in order]
