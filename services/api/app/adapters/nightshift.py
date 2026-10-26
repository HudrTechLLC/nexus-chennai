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
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import FORBIDDEN_MODELS, Settings
from ..tracing import Tracer


class NightshiftError(RuntimeError):
    """Nightshift returned an error or could not be reached."""


class NightshiftUnauthorized(NightshiftError):
    """401/403: the runtime token is missing or wrong."""


class LaneNotConfigured(NightshiftError):
    """The requested lane has no pinned model in the environment."""


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
        self._client = httpx.Client(
            base_url=settings.meterless_base_url.rstrip("/"),
            timeout=settings.nightshift_timeout_seconds,
            transport=transport,
        )

    # ----- helpers -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.meterless_runtime_token}",
            "meterless-app": self.settings.meterless_app,
            "meterless-scope": "user",
        }

    def model_for(self, lane: str) -> str:
        model = self.settings.lanes.get(lane)
        if not model:
            raise LaneNotConfigured(f"Lane '{lane}' has no pinned model (set LANE_{lane.upper()})")
        if model in FORBIDDEN_MODELS:
            raise LaneNotConfigured(f"Lane '{lane}' is set to {model}; pin an exact model (rule R2)")
        return model

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        resp = self._client.post(path, json=body, headers=self._headers())
        if resp.status_code in (401, 403):
            raise NightshiftUnauthorized(f"Nightshift rejected the runtime token (HTTP {resp.status_code})")
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
        try:
            resp = self._post("/chat/completions", {"model": model, "messages": messages, **params})
        except (httpx.TransportError, NightshiftError, httpx.HTTPStatusError) as exc:
            # Replay only when Nightshift is unreachable or failing (transport / 5xx).
            # A 4xx (bad token, unknown model id) is a real answer and must surface.
            if self.settings.sample_mode and _is_retryable(exc):
                return self._replay(lane, model, messages, agent, purpose, started)
            self._trace(agent, purpose, lane, model, None, None, status="error", note=str(exc))
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
        return self.fixtures_dir / f"{fixture_key(lane, messages)}.json"

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
