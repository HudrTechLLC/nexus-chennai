"""Nexus API (FastAPI). Judge entry point: POST /run (spec Part H)."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .adapters.nightshift import NightshiftClient, NightshiftError
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient, ZetarisError
from .config import REPO_ROOT, Settings, get_settings, load_city
from .feeds import router as feeds_router
from .agents import AgentError, Briefer, Sanitiser, SeriesAnalyst
from .agents.base import crime_from_row, features_from_row
from .agents.series import dossier_record
from .graph.runner import CaseNotFound, agent_deps, default_store, run_request
from .graph.store import SupabaseStore
from .tracing import new_run_id

app = FastAPI(title="Nexus Chennai API", version="0.1.0")
app.include_router(feeds_router)  # GET /mock-feeds/news|social (WS1-16, nexus-2)


class RunInput(BaseModel):
    """Part H: `{kind, ...}`. Fields may sit in `payload` or directly beside `kind`."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["case", "batch", "tip", "search"]
    payload: dict[str, Any] = Field(default_factory=dict)

    def merged_payload(self) -> dict[str, Any]:
        return {**(self.model_extra or {}), **self.payload}


class RunOptions(BaseModel):
    sample_mode: bool | None = None
    force_extract: bool = False
    persist: bool = True


class RunRequest(BaseModel):
    run_id: str | None = None
    input: RunInput
    options: RunOptions = Field(default_factory=RunOptions)


HEALTH_PROBE_SECONDS = 1.5  # per adapter: one attempt with this timeout, no retries
HEALTH_BUDGET_SECONDS = 2.0  # the whole endpoint; a probe still running then is reported down
_health_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="health")


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def _probe_zetaris(s: Settings) -> dict[str, Any]:
    if s.sample_mode and not s.zetaris_api_key:  # the adapter goes straight to the DuckDB twins (no Zetaris call)
        return {"state": "sample", "reason": "sample mode without Zetaris credentials"}
    z = ZetarisClient(s)
    try:
        r = z.named("q_ping", agent="health")
        return {"state": "sample" if r.source == "sample" else "live", "ms": r.ms}
    finally:
        z.close()


def _probe_nightshift(s: Settings) -> dict[str, Any]:
    n = NightshiftClient(s)
    try:  # GET /v1/models only: never a model call from /health
        return {"state": "live", "models_available": len(n.list_models()), "lanes": s.lanes}
    finally:
        n.close()


def _probe_supabase(s: Settings) -> dict[str, Any]:
    sb = SupabaseClient(s)
    try:
        if not sb.configured:  # sample runs keep results in memory
            return {"state": "sample" if s.sample_mode else "down", "error": "NotConfigured"}
        sb._client.timeout = httpx.Timeout(HEALTH_PROBE_SECONDS)
        return {"state": "live"} if sb.health() else {"state": "down", "error": "HealthCheckFailed"}
    finally:
        sb.close()


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness plus each connector's state (live / sample / down + error class), within ~2 s.

    Probes run concurrently with a 1.5 s timeout each and no retries; anything slower is reported down,
    so judges and the CI docker job never wait on an unreachable service.
    """
    s = get_settings()
    fast = s.model_copy(update={"zetaris_timeout_seconds": HEALTH_PROBE_SECONDS,
                                "nightshift_timeout_seconds": HEALTH_PROBE_SECONDS})
    probes = {"zetaris": _probe_zetaris, "nightshift": _probe_nightshift, "supabase": _probe_supabase}
    futures = {name: _health_pool.submit(fn, fast) for name, fn in probes.items()}
    deadline = time.monotonic() + HEALTH_BUDGET_SECONDS
    adapters: dict[str, Any] = {}
    for name, fut in futures.items():
        try:
            adapters[name] = fut.result(timeout=max(0.0, deadline - time.monotonic()))
        except FutureTimeout:
            fut.cancel()
            adapters[name] = {"state": "down", "error": f"TimeoutError: no answer in {HEALTH_PROBE_SECONDS:g}s"}
        except Exception as exc:  # health must never raise
            adapters[name] = {"state": "down", "error": _err(exc)}
    ns = adapters["nightshift"]
    if ns["state"] == "down":
        ns["lanes"] = s.lanes
        if s.sample_mode:  # sample mode replays recorded model outputs; Nightshift is optional
            ns["state"] = "sample"
    city = load_city(s.city)
    return {"status": "ok", "city": city.get("name"), "sample_mode": s.sample_mode, "adapters": adapters}


@app.post("/run")
def run(req: RunRequest) -> dict[str, Any]:
    """Judge entry point: runs the C4 agent graph and returns alerts, trace id, log file and timing."""
    s = get_settings()
    run_id = req.run_id or new_run_id()
    try:
        return run_request(req.input.kind, req.input.merged_payload(), req.options.model_dump(), s, run_id=run_id)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail={"run_id": run_id, "status": "not_found", "message": str(exc),
                                                     "log_file": f"logs/trace-{run_id}.jsonl"})
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"run_id": run_id, "status": "bad_input", "message": str(exc)})
    except (ZetarisError, NightshiftError) as exc:
        raise HTTPException(status_code=503, detail={"run_id": run_id, "status": "dependency_down",
                                                     "message": str(exc), "log_file": f"logs/trace-{run_id}.jsonl"})


# ----- Part H: agent endpoints --------------------------------------------------------


@app.post("/api/cases/{crime_id}/process")
def process_case(crime_id: str, options: RunOptions | None = None) -> dict[str, Any]:
    """Extract -> link -> Skeptic -> alerts for one case (same graph as /run)."""
    return run(RunRequest(input=RunInput(kind="case", payload={"crime_id": crime_id}),
                          options=options or RunOptions()))


class BatchBody(BaseModel):
    crime_ids: list[str]
    options: RunOptions = Field(default_factory=RunOptions)


@app.post("/api/batch/link")
def batch_link(body: BatchBody) -> dict[str, Any]:
    return run(RunRequest(input=RunInput(kind="batch", payload={"crime_ids": body.crime_ids}), options=body.options))


def _case_and_features(deps, crime_id: str):
    rows, _ = deps.query("q_case", agent="api", crime_id=crime_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"case {crime_id} not found")
    frows, _ = deps.query("q_features", agent="api", ids=crime_id)
    return crime_from_row(rows[0]), (features_from_row(frows[0]) if frows else None)


@app.post("/api/cases/{crime_id}/public-draft")
def public_draft(crime_id: str) -> dict[str, Any]:
    """Sanitiser draft of a public appeal. A draft only: an officer must publish it."""
    s = get_settings()
    run_id = new_run_id("draft")
    with agent_deps(s, run_id) as deps:
        case, feats = _case_and_features(deps, crime_id)
        try:
            draft = Sanitiser(deps).draft(case, feats)
        except AgentError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    return {**draft, "run_id": run_id, "log_file": f"logs/trace-{run_id}.jsonl"}


class DossierBody(BaseModel):
    crime_ids: list[str] = Field(min_length=1)
    persist: bool = True


@app.post("/api/series/{series_id}/dossier")
def series_dossier(series_id: str, body: DossierBody) -> dict[str, Any]:
    """Markovian series dossier over every case, statement, evidence tag and clean tip of the series."""
    s = get_settings()
    run_id = new_run_id("dossier")
    with agent_deps(s, run_id) as deps:
        try:
            out = SeriesAnalyst(deps).dossier(series_id, body.crime_ids)
        except AgentError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        persisted = False
        if body.persist:
            try:  # series.dossier for the console (Vercel cannot call this API); a stored series row only
                store = default_store(s, deps.tracer)
                persisted = store.write_dossier(series_id, dossier_record(out, run_id)) and isinstance(
                    store, SupabaseStore)
            except Exception as exc:
                deps.tracer.emit("Series analyst", "dossier_save_failed", input_summary=series_id,
                                 output_summary=str(exc)[:300], status="error")
    return {**out, "run_id": run_id, "persisted": persisted, "log_file": f"logs/trace-{run_id}.jsonl"}


class BriefingBody(BaseModel):
    zone: str
    day: str
    alerts: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []


@app.post("/api/briefing")
def briefing(body: BriefingBody) -> dict[str, Any]:
    """Zone briefing (Briefer): numbers from code, prose from the tiny/fast lane."""
    s = get_settings()
    run_id = new_run_id("brief")
    with agent_deps(s, run_id) as deps:
        out = Briefer(deps).brief(body.zone, body.day, body.alerts, body.decisions)
    return {**out, "run_id": run_id}


@app.get("/api/traces/{run_id}")
def traces(run_id: str) -> dict[str, Any]:
    """Trace events of one run, exactly as written (D3.12)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise HTTPException(status_code=400, detail="bad run id")
    path = REPO_ROOT / "logs" / f"trace-{run_id}.jsonl"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="no trace for this run")
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"run_id": run_id, "events": events, "log_file": f"logs/trace-{run_id}.jsonl"}


__all__ = ["app", "NightshiftError"]
