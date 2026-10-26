"""Suite-wide isolation: no test may read or write the real data/local/ store (WS2-22).

Live-mode runs without Supabase now default to the file-backed LocalStore. Each test gets its own
empty store directory, and the cached settings are cleared so the env var takes effect.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_local_store(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("NEXUS_LOCAL_DIR", str(tmp_path_factory.mktemp("local_store")))
    monkeypatch.delenv("NEXUS_STORE", raising=False)
    try:
        from app.config import get_settings
    except ImportError:  # suites that do not put services/api on the path
        yield
        return
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
