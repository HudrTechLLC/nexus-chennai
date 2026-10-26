"""Shared fixtures. Every engines test runs on a fresh store, a temp trace and temp memory,
once per backend:

- `sample`: the in-process Python backend (always runs);
- `sidecar`: the vendored Meterless TypeScript references via engines-ts/sidecar.

With ENGINES_BACKEND=sidecar in the environment (the CI `engines` job), only the sidecar
backend runs and an unreachable sidecar is a failure. Otherwise the sidecar cases run when
a sidecar answers at ENGINES_SIDECAR_URL, and are skipped when none does.
"""

import functools
import os

import httpx
import pytest

from app.engines import hmem, set_tracer, world_model
from app.engines._runtime import sidecar_url
from app.tracing import Tracer

REQUIRE_SIDECAR = os.environ.get("ENGINES_BACKEND", "").strip().lower() == "sidecar"
BACKENDS = ["sidecar"] if REQUIRE_SIDECAR else ["sample", "sidecar"]


@functools.cache
def _sidecar_up() -> bool:
    from app.engines._sidecar import _client

    try:
        return _client.get(f"{sidecar_url()}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def CLOCK():
    return 1_790_000_000_000


@pytest.fixture(autouse=True, params=BACKENDS)
def engine_backend(request, tmp_path, monkeypatch):
    if request.param == "sidecar" and not _sidecar_up():
        if REQUIRE_SIDECAR:
            pytest.fail(f"ENGINES_BACKEND=sidecar but no sidecar at {sidecar_url()}")
        pytest.skip("engines sidecar not running (cd engines-ts && npm run sidecar)")
    monkeypatch.setenv("ENGINES_BACKEND", request.param)
    tracer = Tracer("test", tmp_path / "logs", echo=False)
    set_tracer(tracer)
    world_model.reset()
    hmem.configure(tmp_path / "hmem", clock=CLOCK)
    yield request.param
    set_tracer(None)


@pytest.fixture
def tracer(engine_backend):
    from app.engines import get_tracer

    return get_tracer()


def events(tracer, engine=None):
    return [e for e in tracer.read() if engine is None or e["engine"] == engine]
