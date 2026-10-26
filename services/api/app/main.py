"""Nexus API (FastAPI). Judge entry point: POST /run (spec Part H)."""

from __future__ import annotations

import json
import re

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .adapters.nightshift import NightshiftClient, NightshiftError
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient, ZetarisError
from .config import REPO_ROOT, get_settings, load_city
from .feeds import router as feeds_router
from .agents import AgentError, Briefer, Sanitiser, SeriesAnalyst
from .agents.base import crime_from_row, features_from_row
from .graph.runner import agent_deps, run_request
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


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness plus which adapters are live, in sample mode or down."""
    s = get_settings()
    city = load_city(s.city)
    status: dict[str, Any] = {"status": "ok", "city": city.get("name"), "sample_mode": s.sample_mode, "adapters": {}}

    z = ZetarisClient(s)
    try:
        r = z.named("q_ping", agent="health")
        status["adapters"]["zetaris"] = "sample" if r.source == "sample" else "live"
    except ZetarisError as exc:
        status["adapters"]["zetaris"] = f"down: {exc}"
    finally:
        z.close()

    n = NightshiftClient(s)
    try:
        models = n.list_models()
        status["adapters"]["nightshift"] = {"state": "live", "models_available": len(models), "lanes": s.lanes}
    except Exception as exc:  # health must never raise
        status["adapters"]["nightshift"] = {"state": "sample" if s.sample_mode else f"down: {exc}", "lanes": s.lanes}
    finally:
        n.close()

    sb = SupabaseClient(s)
    try:
        status["adapters"]["supabase"] = "live" if sb.health() else "not configured or down"
    except Exception as exc:
        status["adapters"]["supabase"] = f"down: {exc}"
    finally:
        sb.close()
    return status


@app.post("/run")
def run(req: RunRequest) -> dict[str, Any]:
    """Judge entry point: runs the C4 agent graph and returns alerts, trace id, log file and timing."""
    s = get_settings()
    run_id = req.run_id or new_run_id()
    try:
        return run_request(req.input.kind, req.input.merged_payload(), req.options.model_dump(), s, run_id=run_id)
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
    return {**out, "run_id": run_id, "log_file": f"logs/trace-{run_id}.jsonl"}


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
