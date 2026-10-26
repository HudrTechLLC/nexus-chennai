"""Nexus API (FastAPI). Judge entry point: POST /run (spec Part H)."""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .adapters.nightshift import NightshiftClient, NightshiftError
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient, ZetarisError
from .config import get_settings, load_city
from .tracing import Tracer, new_run_id

app = FastAPI(title="Nexus Chennai API", version="0.1.0")


class RunInput(BaseModel):
    kind: Literal["case", "batch", "tip", "search"]
    payload: dict[str, Any] = Field(default_factory=dict)


class RunOptions(BaseModel):
    sample_mode: bool | None = None


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
    """Judge entry point. The agent graph lands in P3/P4; until then this says so plainly."""
    s = get_settings()
    run_id = req.run_id or new_run_id()
    tracer = Tracer(run_id, s.logs_dir)
    started = time.perf_counter()
    tracer.emit("api", "run_received", input_summary=f"kind={req.input.kind}", status="ok")
    tracer.emit("api", "run_rejected", output_summary="agent graph not built yet (phase P4)", status="not_implemented")
    raise HTTPException(
        status_code=501,
        detail={
            "run_id": run_id,
            "status": "not_implemented",
            "message": "The agent graph is built in phase P4. No output is faked.",
            "log_file": str(tracer.path.relative_to(s.logs_dir.parent)),
            "execution_time_seconds": round(time.perf_counter() - started, 3),
        },
    )


__all__ = ["app", "NightshiftError"]
