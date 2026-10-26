"""Shared runtime for the engines facade: tracing and backend selection.

Every facade call emits one trace event (spec D3.12) with `engine` set. The caller
(the LangGraph run) binds its run's Tracer with `use_tracer`. Without one, events go
to a default `engines` tracer under logs/, so the rule "every call emits a trace"
holds unconditionally.

Backends (env `ENGINES_BACKEND`):
- `sample` (default): the engine logic runs in-process (Python ports of the
  Meterless reference algorithms, see each engine's `core.py`).
- `sidecar`: calls the vendored TypeScript references in `engines-ts/sidecar`
  over HTTP (`ENGINES_SIDECAR_URL`, default http://127.0.0.1:8790).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from app.tracing import Tracer, new_run_id

ENGINE_NAMES = ("world_model", "hmem", "markovian", "scout_intent")
BACKENDS = ("sample", "sidecar")

_current: ContextVar[Tracer | None] = ContextVar("engines_tracer", default=None)
_default: Tracer | None = None


def _logs_dir():
    from app.config import get_settings

    return get_settings().logs_dir


def get_tracer() -> Tracer:
    """The bound tracer, or a lazily created default one."""
    global _default
    tracer = _current.get()
    if tracer is not None:
        return tracer
    if _default is None:
        _default = Tracer(new_run_id("engines"), _logs_dir(), echo=False)
    return _default


def set_tracer(tracer: Tracer | None) -> None:
    """Bind a tracer for the current context (None unbinds)."""
    _current.set(tracer)


@contextmanager
def use_tracer(tracer: Tracer) -> Iterator[Tracer]:
    """Bind `tracer` for the duration of a block."""
    token = _current.set(tracer)
    try:
        yield tracer
    finally:
        _current.reset(token)


def emit(engine: str, action: str, input_summary: str, output_summary: str, **fields: Any) -> dict[str, Any]:
    if engine not in ENGINE_NAMES:
        raise ValueError(f"unknown engine {engine!r}")
    fields.setdefault("status", "ok")
    return get_tracer().emit(
        "Engines",
        action,
        engine=engine,
        input_summary=input_summary[:300],
        output_summary=output_summary[:300],
        **fields,
    )


def backend() -> str:
    value = os.environ.get("ENGINES_BACKEND", "sample").strip().lower() or "sample"
    if value not in BACKENDS:
        raise ValueError(f"ENGINES_BACKEND must be one of {BACKENDS}, got {value!r}")
    return value


def sidecar_url() -> str:
    return os.environ.get("ENGINES_SIDECAR_URL", "http://127.0.0.1:8790").rstrip("/")
