"""D3 models validate the spec's own examples, read straight from engg/docs/SPEC.md.

Reading the examples from the spec (not copies) means a renamed field in either place
fails here. The spec uses "…" placeholders and "a|b" enum hints; `_fill` swaps them
for concrete values and every swap is listed below.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import models as m
from app.tracing import EVENT_FIELDS

SPEC = Path(__file__).resolve().parents[2] / "engg" / "docs" / "SPEC.md"
TS = "2026-10-14T19:44:12+05:30"
# Keys whose "…" placeholder must become a timestamp.
TIME_KEYS = {"at", "created_at", "published_at", "recorded_at", "captured_at", "received_at", "timestamp"}
# "a|b|c" enum hints in the spec examples -> the value used in the test.
ENUM_PICKS = {"pair|series|hotspot": "pair", "pending|approved|rejected": "rejected", "text|audio": "text"}


def _section(num: str) -> str:
    text = SPEC.read_text(encoding="utf-8")
    start = text.index(f"### D3.{num} ")
    nxt = re.search(r"\n#{2,3} ", text[start + 5:])
    return text[start: start + 5 + nxt.start()] if nxt else text[start:]


def _code_blocks(num: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", _section(num), flags=re.S)


def _fill(obj, key: str | None = None):
    if isinstance(obj, dict):
        return {k: _fill(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, key) for v in obj]
    if isinstance(obj, str):
        if obj in ENUM_PICKS:
            return ENUM_PICKS[obj]
        if obj == "…" and key in TIME_KEYS:
            return TS
    return obj


def _example(num: str) -> dict:
    return _fill(json.loads(_code_blocks(num)[0]))


def _csv_rows(block: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(block.strip()), skipinitialspace=True))


# ---------- JSON examples ----------
def test_d3_1_crime():
    c = m.Crime.model_validate(_example("1"))
    assert c.crime_id == "CHN-AD-2026-001182"
    assert c.vehicles[0].plate == "TN 09 ?? 4471"
    assert c.occurred_from.utcoffset().total_seconds() == 5.5 * 3600


def test_d3_2_features():
    f = m.CrimeFeatures.model_validate(_example("2"))
    assert f.mo.place_type == ["bus_stop", "main_road"]


def test_d3_4_evidence():
    e = m.EvidenceMedia.model_validate(_example("4"))
    assert e.vision.plate_confidence == 0.58


def test_d3_5_statement():
    assert m.WitnessStatement.model_validate(_example("5")).mode == "text"


def test_d3_6_tip():
    t = m.Tip.model_validate(_example("6"))
    assert t.guard.verdict == "clean" and t.received_week == "2026-W43"


def test_d3_7_news():
    assert m.NewsArticle.model_validate(_example("7")).places_mentioned == ["Adyar", "L.B. Road"]


def test_d3_8_call():
    assert m.CallLog.model_validate(_example("8")).caller == "masked"


def test_d3_11_alert():
    raw = _example("11")
    # Spec inconsistency: the D3.11 example names the factor "weapon"; F2 calls it "weapon_tool".
    for f in raw["factors"]:
        if f["factor"] == "weapon":
            f["factor"] = "weapon_tool"
    a = m.LinkAlert.model_validate(raw)
    assert a.band == m.band_for(a.score) == "high"
    assert [f.factor for f in a.factors if f.struck_by_skeptic] == ["weapon_tool"]


def test_d3_12_trace_event_matches_tracer():
    ev = m.TraceEvent.model_validate(_example("12"))
    assert ev.agent_name == "Skeptic"
    assert set(m.TraceEvent.model_fields) - {"extra"} == set(EVENT_FIELDS)


def test_d3_13_public_incident():
    p = m.PublicIncident.model_validate(_example("13"))
    assert "crime_id" not in m.PublicIncident.model_fields
    assert p.images[0].blurred is True


# ---------- CSV examples ----------
def test_d3_3_legacy_cctns_row():
    row = _csv_rows(_code_blocks("3")[0])[0]
    r = m.LegacyCctnsRow.model_validate(row)
    assert r.FIR_DT == "12-03-2024" and r.LONG == 80.2209


def test_d3_9_anpr_read():
    row = _csv_rows(_code_blocks("9")[0])[0]
    assert m.AnprRead.model_validate(row).plate_text == "TN09BX4471"


def test_d3_10_camera_and_release():
    cam_block, rel_block = _code_blocks("10")[0].strip().split("\n\n")
    cam = m.CctvCamera.model_validate(_csv_rows(cam_block)[0])
    rel = m.Release.model_validate(_csv_rows(rel_block)[0])
    assert cam.retention_days == 15
    assert rel.prior_mo_tags == ["night_house_break", "grille_cut"]


def test_history_sheet_minimal():
    h = m.HistorySheet(sheet_id="HS-1", person_ref="P-1", station_id="PS-X", opened_on="2024-01-02",
                       category="property_offender", mo_tags="grille_cut;night_house_break")
    assert h.mo_tags == ["grille_cut", "night_house_break"]


# ---------- strictness ----------
def test_unknown_field_is_rejected():
    raw = _example("1")
    raw["stationId"] = "PS-ADYAR-J2"
    with pytest.raises(ValidationError):
        m.Crime.model_validate(raw)


def test_naive_timestamp_is_rejected():
    raw = _example("1")
    raw["reported_at"] = "2026-10-14T21:05:00"
    with pytest.raises(ValidationError):
        m.Crime.model_validate(raw)


def test_unknown_factor_is_rejected():
    with pytest.raises(ValidationError):
        m.LinkFactor(factor="weapon", weight=0.08, value=0, reason="x")


def test_bands():
    assert m.band_for(0.75) == "high"
    assert m.band_for(0.55) == "medium"
    assert m.band_for(0.549) is None
    assert sum(m.FACTOR_WEIGHTS.values()) == pytest.approx(1.0)


def test_rejection_needs_reason():
    with pytest.raises(ValidationError):
        m.AlertDecision(alert_id="LA-1", decision="reject", by="u", at=TS)
    ok = m.AlertDecision(alert_id="LA-1", decision="reject", reason_code="different_mo", by="u", at=TS)
    assert ok.reason_code in m.REJECTION_REASONS


def test_pending_alert_cannot_carry_decision():
    raw = _example("11")
    raw["factors"] = []
    raw["status"] = "pending"
    with pytest.raises(ValidationError):
        m.LinkAlert.model_validate(raw)


def test_tip_week_format():
    raw = _example("6")
    raw["received_week"] = "2026-10-14"
    with pytest.raises(ValidationError):
        m.Tip.model_validate(raw)


def test_evidence_ref_carries_query_and_alert_coverage():
    raw = _example("11")
    for f in raw["factors"]:
        if f["factor"] == "weapon":
            f["factor"] = "weapon_tool"
        for ev in f.get("evidence", []):
            ev.update(query="q_vehicle_trail", query_id="q_8812")
    raw["coverage"] = 0.63
    a = m.LinkAlert.model_validate(raw)
    assert a.coverage == 0.63 and a.factors[0].evidence[0].query_id == "q_8812"
