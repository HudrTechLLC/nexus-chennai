"""Hotspot detector (nexus-2) wired into /run output and the Alert writer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from agents_fixtures import ADYAR, FakeNightshift, FakeZetaris, default_handlers  # noqa: E402

from app.agents.alert_writer import hotspot_id_for  # noqa: E402
from app.agents.briefer import briefing_facts  # noqa: E402
from app.config import Settings  # noqa: E402
from app.graph import run_request  # noqa: E402
from app.models import LinkAlert  # noqa: E402


def hex_rows(p):
    """Planted cluster: 6 chain snatchings in one cell in the window (incl. the hero case), none before."""
    ids = [ADYAR["crime_id"]] + [f"CHN-AD-2026-9{i:05d}" for i in range(5)]
    return [{"cell": "8961abc", "category": "robbery", "day": "2026-10-14", "n": 6,
             "crime_ids": json.dumps(ids), "station_ids": json.dumps(["PS-ADYAR-J2"])},
            {"cell": "89xxxxx", "category": "robbery", "day": "2026-09-01", "n": 1,
             "crime_ids": json.dumps(["OTHER"]), "station_ids": json.dumps(["PS-X"])}]


def run(tmp_path, monkeypatch, handlers, **opts):
    monkeypatch.setattr(Settings, "logs_dir", property(lambda self: tmp_path / "logs"))
    return run_request("case", {"crime_id": ADYAR["crime_id"]}, opts, Settings(_env_file=None),
                       zetaris=FakeZetaris(handlers), nightshift=FakeNightshift(lambda *a: "{}"))


def test_run_reports_and_writes_hotspot_containing_the_case(tmp_path, monkeypatch):
    h = default_handlers()
    h["q_hex_counts"] = hex_rows
    out = run(tmp_path, monkeypatch, h)
    hs = out["output"]["hotspots"]
    assert len(hs) == 1 and hs[0]["kind"] == "hotspot" and hs[0]["band"] == "high"
    assert hs[0]["alert_id"] == hotspot_id_for(hs[0]) and hs[0]["observed"] == 6
    assert ADYAR["crime_id"] in hs[0]["crimes"]
    LinkAlert.model_validate({k: hs[0][k] for k in ("alert_id", "kind", "crimes", "stations", "score", "band",
                                                     "rationale", "status")} | {"run_id": "r",
                                                                                "created_at": "2026-10-26T00:00:00+05:30"})


def test_hotspots_can_be_switched_off_and_failures_do_not_break_the_run(tmp_path, monkeypatch):
    h = default_handlers()
    h["q_hex_counts"] = hex_rows
    assert run(tmp_path, monkeypatch, h, hotspots=False)["output"]["hotspots"] == []
    h2 = default_handlers()
    del h2["q_hex_counts"]
    out = run(tmp_path, monkeypatch, h2)
    assert out["status"] == "success" and out["output"]["hotspots"] == []
    assert any("hotspots" in e for e in out["output"]["errors"])


def test_briefer_counts_hotspots_separately():
    f = briefing_facts("South", "d", [{"kind": "hotspot", "status": "pending", "rationale": "6 in cell"},
                                      {"kind": "pair", "band": "high", "status": "pending"}], [])
    assert f["hotspots"] == 1 and f["new_alerts"] == 1
