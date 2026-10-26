"""Shared fixtures: every engines test runs against a fresh store, a temp trace and temp memory."""

import pytest

from app.engines import hmem, set_tracer, world_model
from app.tracing import Tracer


@pytest.fixture(autouse=True)
def isolated_engines(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINES_BACKEND", "sample")
    tracer = Tracer("test", tmp_path / "logs", echo=False)
    set_tracer(tracer)
    world_model.reset()
    hmem.configure(tmp_path / "hmem", clock=lambda: 1_790_000_000_000)
    yield tracer
    set_tracer(None)


@pytest.fixture
def tracer(isolated_engines):
    return isolated_engines


def events(tracer, engine=None):
    return [e for e in tracer.read() if engine is None or e["engine"] == engine]
