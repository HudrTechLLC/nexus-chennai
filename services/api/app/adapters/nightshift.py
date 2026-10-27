"""Meterless Nightshift adapter: the only path for model calls (rule R2).

Contract (Meterless Runtime 0.90.0, engg/docs/SETUP.md):
- OpenAI-compatible API at METERLESS_BASE_URL (default http://127.0.0.1:8088/v1).
- Bearer runtime token, plus headers `meterless-app` and `meterless-scope: user`.
- 401/403 means a bad token. Timeout is 180 s.

Every call uses a pinned lane model (never `meterless/auto`). It logs the lane, the
pinned model, the model Nightshift reports in its response (`routed_model`) and any
receipt id, so the trace shows which model handled each request.

Sample mode, when Nightshift is unreachable, replays model output previously
recorded from live calls in data/sample/model_fixtures/. Those trace lines are
labelled `replayed`; the agent logic around them still runs (rule R6). With no
recorded fixture the call fails. It never invents an answer.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import FORBIDDEN_MODELS, Settings
from ..tracing import Tracer


class NightshiftError(RuntimeError):
    """Nightshift returned an error or could not be reached."""


class NightshiftUnauthorized(NightshiftError):
    """401/403: the runtime token is missing or wrong."""


class LaneNotConfigured(NightshiftError):
    """The requested lane has no pinned model in the environment."""


class NightshiftRefused(NightshiftError):
    """A deterministic refusal (e.g. no_vision_model: no configured model admits images). An answer, not an outage:
    never retried, and the body's reason is kept in the message so callers can trace it."""


class NightshiftEmptyResponse(NightshiftError):
    """The provider answered with no content (e.g. the cloud vision route with too small a max_tokens). Not retried
    as-is here: the same request comes back empty again. chat_json retries it once with more room."""


REFUSALS = ("no_vision_model",)
EMPTY_RESPONSES = ("_empty_response",)


@dataclass
class ModelResult:
    lane: str
    model: str
    routed_model: str | None
    content: str
    receipt_id: str | None
    replayed: bool
    latency_ms: int
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


RATE_LIMITED = 429
RETRY_AFTER_CAP_SECONDS = 20.0  # two capped waits stay well inside a live case's deadline
_backoff = wait_exponential(multiplier=0.5, max=4)


def _is_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == RATE_LIMITED


def _should_retry(exc: BaseException) -> bool:
    """Transport errors, 5xx and 429 are retried. 429 is kept out of `_is_retryable`, which also decides the
    sample-mode replay: being rate-limited is not an outage, so it must not swap a live answer for a fixture."""
    return _is_retryable(exc) or _is_rate_limited(exc)


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    """Retry-After as seconds (RFC 9110: delta-seconds or an HTTP-date), clamped to [0, cap]; None if absent or
    unparseable."""
    if value is None or not value.strip():
        return None
    v = value.strip()
    try:
        secs = float(v)
    except ValueError:
        try:
            when = parsedate_to_datetime(v)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        secs = (when - (now or datetime.now(timezone.utc))).total_seconds()
    if secs != secs:  # NaN
        return None
    return max(0.0, min(RETRY_AFTER_CAP_SECONDS, secs))


def _wait(state: RetryCallState) -> float:
    """Honour a 429's Retry-After when it has one; otherwise the usual exponential backoff."""
    exc = state.outcome.exception() if state.outcome else None
    if _is_rate_limited(exc):
        secs = retry_after_seconds(exc.response.headers.get("Retry-After"))
        if secs is not None:
            return secs
    return _backoff(state)


def fixture_key(lane: str, messages: list[dict[str, Any]]) -> str:
    canonical = json.dumps({"lane": lane, "messages": messages}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


class NightshiftClient:
    def __init__(
        self,
        settings: Settings,
        tracer: Tracer | None = None,
        transport: httpx.BaseTransport | None = None,
        fixtures_dir: Path | None = None,
        record_fixtures: bool = False,
    ) -> None:
        self.settings = settings
        self.tracer = tracer
        self.fixtures_dir = fixtures_dir or settings.sample_dir / "model_fixtures"
        self.record_fixtures = record_fixtures
        # n-th identical request in this client (one client per run): recorded and replayed in order.
        self._occurrence: dict[str, int] = {}
        self._client = httpx.Client(
            base_url=settings.meterless_base_url.rstrip("/"),
            timeout=settings.nightshift_timeout_seconds,
            transport=transport,
        )

    # ----- helpers -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"meterless-app": self.settings.meterless_app, "meterless-scope": "user"}
        token = (self.settings.meterless_runtime_token or "").strip()
        if token:  # never send an empty "Bearer " (an illegal header value)
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def model_for(self, lane: str) -> str:
        model = self.settings.lanes.get(lane)
        if not model:
            raise LaneNotConfigured(f"Lane '{lane}' has no pinned model (set LANE_{lane.upper()})")
        if model in FORBIDDEN_MODELS:
            raise LaneNotConfigured(f"Lane '{lane}' is set to {model}; pin an exact model (rule R2)")
        return model

    @retry(
        retry=retry_if_exception(_should_retry),
        stop=stop_after_attempt(3),
        wait=_wait,
        reraise=True,
    )
    def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        resp = self._client.post(path, json=body, headers=self._headers())
        if resp.status_code in (401, 403):
            raise NightshiftUnauthorized(f"Nightshift rejected the runtime token (HTTP {resp.status_code})")
        if resp.status_code >= 400 and any(r in resp.text for r in REFUSALS):
            raise NightshiftRefused(f"HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code >= 400 and any(r in resp.text for r in EMPTY_RESPONSES):
            raise NightshiftEmptyResponse(f"HTTP {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp

    # ----- public API ----------------------------------------------------

    def list_models(self) -> list[str]:
        resp = self._client.get("/models", headers=self._headers())
        if resp.status_code in (401, 403):
            raise NightshiftUnauthorized(f"Nightshift rejected the runtime token (HTTP {resp.status_code})")
        resp.raise_for_status()
        return [m.get("id", "") for m in resp.json().get("data", [])]

    def chat(
        self,
        lane: str,
        messages: list[dict[str, Any]],
        *,
        agent: str,
        purpose: str = "",
        **params: Any,
    ) -> ModelResult:
        """One chat completion on a pinned lane. Every call emits a trace event."""
        model = self.model_for(lane)
        started = time.perf_counter()
        if self.settings.sample_mode and not (self.settings.meterless_runtime_token or "").strip():
            # Sample mode with no Nightshift credentials: there is nothing live to call,
            # so go straight to the recorded output (labelled `replayed`, rule R6).
            return self._replay(lane, model, messages, agent, purpose, started)
        try:
            resp = self._post("/chat/completions", {"model": model, "messages": messages, **params})
        except (httpx.TransportError, NightshiftError, httpx.HTTPStatusError) as exc:
            # Replay only when Nightshift is unreachable or failing (transport / 5xx).
            # A 4xx (bad token, unknown model id) is a real answer and must surface.
            if self.settings.sample_mode and _is_retryable(exc):
                return self._replay(lane, model, messages, agent, purpose, started)
            self._trace(agent, purpose, lane, model, None, None, status="error", note=str(exc))
            if isinstance(exc, NightshiftEmptyResponse):
                raise  # the caller retries it with more room
            raise NightshiftError(str(exc)) from exc

        data = resp.json()
        result = ModelResult(
            lane=lane,
            model=model,
            routed_model=data.get("model"),
            content=(data.get("choices") or [{}])[0].get("message", {}).get("content") or "",
            receipt_id=self._receipt_id(resp, data),
            replayed=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=data.get("usage") or {},
            raw=data,
        )
        if self.record_fixtures:
            self._save_fixture(lane, messages, data)
        self._trace(agent, purpose, lane, model, result.routed_model, result.receipt_id, status="ok", note=f"{result.latency_ms} ms")
        return result

    # ----- internals -----------------------------------------------------

    @staticmethod
    def _receipt_id(resp: httpx.Response, data: dict[str, Any]) -> str | None:
        # The receipt format is not documented yet (DECISIONS D-006). Prefer a
        # meterless receipt header, then any receipt field, then the response id.
        for name, value in resp.headers.items():
            if name.lower().startswith(("meterless-receipt", "x-meterless-receipt")):
                return value
        for key in ("receipt_id", "receipt", "meterless_receipt"):
            if isinstance(data.get(key), str):
                return data[key]
        return data.get("id")

    def _fixture_path(self, lane: str, messages: list[dict[str, Any]]) -> Path:
        """Fixture for this request: <key>.json the first time, <key>-n.json for the n-th identical request
        (an agent may ask the same question twice in a run, e.g. a retry or a second Skeptic round, and get
        a different answer; replay must give the answers back in the same order)."""
        key = fixture_key(lane, messages)
        n = self._occurrence.get(key, 0) + 1
        self._occurrence[key] = n
        return self.fixtures_dir / (f"{key}.json" if n == 1 else f"{key}-{n}.json")

    def _save_fixture(self, lane: str, messages: list[dict[str, Any]], data: dict[str, Any]) -> None:
        path = self._fixture_path(lane, messages)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"lane": lane, "recorded_from": "nightshift", "response": data}, indent=1), encoding="utf-8")

    def _replay(self, lane, model, messages, agent, purpose, started) -> ModelResult:
        path = self._fixture_path(lane, messages)
        if not path.is_file():
            self._trace(agent, purpose, lane, model, None, None, status="error", note="Nightshift down and no recorded fixture")
            raise NightshiftError(f"Nightshift unreachable and no recorded fixture for this request ({path.name})")
        data = json.loads(path.read_text(encoding="utf-8"))["response"]
        result = ModelResult(
            lane=lane,
            model=model,
            routed_model=data.get("model"),
            content=(data.get("choices") or [{}])[0].get("message", {}).get("content") or "",
            receipt_id=data.get("id"),
            replayed=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=data.get("usage") or {},
            raw=data,
        )
        self._trace(agent, purpose, lane, model, result.routed_model, result.receipt_id, status="replayed", note="replayed model output (sample mode)")
        return result

    def _trace(self, agent, purpose, lane, model, routed, receipt, *, status, note="") -> None:
        if self.tracer is None:
            return
        self.tracer.emit(
            agent,
            "model_call",
            input_summary=f"lane={lane} {purpose}".strip(),
            output_summary=note,
            model=model,
            routed_model=routed,
            receipt_id=receipt,
            status=status,
        )

    def close(self) -> None:
        self._client.close()
