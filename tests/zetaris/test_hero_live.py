"""Live Zetaris: the Red Pulsar cross-station hero pair is a blocking candidate. Runs only with NEXUS_LIVE=1
and a Zetaris key file (ZETARIS_API_KEY_FILE, default ~/.secrets/nexus-zetaris.key)."""

import os
from pathlib import Path

import pytest

from app.adapters.zetaris import ZetarisClient
from app.config import Settings
from app.tracing import Tracer

KEY = Path(os.path.expanduser(os.environ.get("ZETARIS_API_KEY_FILE", "~/.secrets/nexus-zetaris.key")))
pytestmark = pytest.mark.skipif(os.environ.get("NEXUS_LIVE") != "1" or not KEY.is_file(), reason="live Zetaris only")


def test_live_hero_cross_station_pair_is_a_candidate(tmp_path):
    c = ZetarisClient(Settings(_env_file=None, sample_mode=False, zetaris_api_key=KEY.read_text().strip()),
                      tracer=Tracer("t", tmp_path, echo=False))
    res = c.named("q_candidates", agent="test", crime_id="CHN-AD-2026-001182", days=45, ring=6)
    assert res.source == "zetaris"
    rows = {r["crime_id"]: r for r in res.dicts()}
    assert "CHN-VL-2026-000877" in rows and rows["CHN-VL-2026-000877"]["same_station"] in (False, "false")
