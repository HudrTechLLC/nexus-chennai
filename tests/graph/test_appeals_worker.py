"""WS4-07: appeal draft requests -> Sanitiser -> public_incidents draft; shared leak fixture (Python side)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_worker_store import FakeSB, worker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from agents_fixtures import ADYAR  # noqa: E402

from app.agents.sanitiser import leak_kind  # noqa: E402

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / "agents" / "appeal_leaks.json").read_text("utf-8"))


@pytest.mark.parametrize("case", FIXTURE["leaky"], ids=lambda c: c["kind"])
def test_leaky_texts_are_caught_with_the_right_kind(case):
    assert leak_kind(case["text"]) == case["kind"]


@pytest.mark.parametrize("text", FIXTURE["clean"])
def test_clean_texts_pass_including_the_spec_example(text):
    assert leak_kind(text) is None


def test_worker_drafts_requested_appeals(tmp_path):
    sb = FakeSB({"appeal_requests": [{"request_id": 1, "crime_id": ADYAR["crime_id"], "status": "requested"},
                                     {"request_id": 2, "crime_id": "NOPE", "status": "requested"},
                                     {"request_id": 3, "crime_id": ADYAR["crime_id"], "status": "drafted"}]})
    w = worker(tmp_path, sb)
    assert w.run_once()["appeals"] == 2
    req = {r["request_id"]: r for r in sb.tables["appeal_requests"]}
    assert req[1]["status"] == "drafted" and req[1]["public_incident_id"]
    assert req[2]["status"] == "failed" and "not found" in req[2]["error"]
    pi = sb.tables["public_incidents"][0]
    assert pi["status"] == "draft" and pi["crime_id"] == ADYAR["crime_id"] and "approved_by" not in pi
    assert pi["public_incident_id"] == req[1]["public_incident_id"]
    text = " ".join([pi["title"], pi["summary"], *pi["looking_for"]])
    assert leak_kind(text) is None
