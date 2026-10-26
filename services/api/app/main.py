"""Nexus API (FastAPI). Judge entry point: POST /run (spec Part H)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .adapters.nightshift import NightshiftClient, NightshiftError
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient, ZetarisError
from .config import get_settings, load_city
from .graph.runner import run_request
from .tracing import new_run_id

app = FastAPI(title="Nexus Chennai API", version="0.1.0")


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


__all__ = ["app", "NightshiftError"]
