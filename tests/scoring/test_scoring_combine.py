"""Unit tests for combining factors into a pair score (app.scoring.combine, weights, baseline)."""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest

from app.scoring import (
    DEFAULT_WEIGHTS,
    FACTORS,
    FactorResult,
    band_for,
    baseline_link,
    cap_memory,
    score_pair,
    strike,
)

# ----- weights -------------------------------------------------------------

SPEC_F2 = {
    "mo_similarity": 0.25,
    "space_time": 0.15,
    "vehicle": 0.15,
    "suspect_description": 0.12,
    "weapon_tool": 0.08,
    "target_profile": 0.05,
    "forensic": 0.08,
    "corroboration": 0.07,
    "offender_return": 0.05,
}


def test_default_weights_match_spec_f2():
    assert dict(DEFAULT_WEIGHTS) == SPEC_F2
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert len(FACTORS) == 9


def test_default_weights_are_read_only():
    with pytest.raises(TypeError):
        DEFAULT_WEIGHTS["mo_similarity"] = 0.9  # type: ignore[index]


# ----- bands ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("score", "band"),
    [(0.75, "high"), (0.7499, "medium"), (0.55, "medium"), (0.5499999999, "medium"), (0.5499, None),
     (0.0, None), (1.0, "high"), (None, None)],
)
def test_band_edges(score, band):
    assert band_for(score) == band


# ----- renormalisation -----------------------------------------------------

def test_score_renormalises_over_factors_with_data():
    p = score_pair([FactorResult("mo_similarity", 0.8), FactorResult("space_time", 0.4),
                    FactorResult("vehicle", None)])
    expected = (0.25 * 0.8 + 0.15 * 0.4) / (0.25 + 0.15)
    assert p.score == pytest.approx(expected, abs=1e-4)
    assert p.base_score == pytest.approx(expected, abs=1e-4)
    assert p.weights_version == "f2-default-v1"


def test_no_data_means_no_score_and_no_alert():
    p = score_pair([FactorResult("vehicle", None), FactorResult("forensic", None)])
    assert p.score is None and p.band is None and p.alert is False


def test_unknown_factor_rejected():
    with pytest.raises(ValueError):
        score_pair([FactorResult("religion", 1.0)])


def test_custom_weights_used_and_labelled():
    p = score_pair([FactorResult("mo_similarity", 1.0), FactorResult("space_time", 0.0)],
                   weights={**SPEC_F2, "mo_similarity": 0.15, "space_time": 0.15})
    assert p.score == pytest.approx(0.5)
    assert p.weights_version == "custom"


def test_values_clipped_into_unit_range():
    p = score_pair([FactorResult("mo_similarity", 1.7)])
    assert p.factors[0].value == 1.0 and p.score == 1.0


def test_output_shape_matches_d3_11_factor_entries():
    p = score_pair([FactorResult("mo_similarity", 0.9, evidence=[{"view": "v_crime_features", "row": "X"}])])
    f = p.to_dict()["factors"][0]
    assert set(f) == {"factor", "weight", "value", "evidence", "struck_by_skeptic", "reason"}
    assert f["weight"] == 0.25 and f["reason"] is None


# ----- Skeptic strikes ------------------------------------------------------

BASE_FACTORS = [
    FactorResult("mo_similarity", 0.91),
    FactorResult("space_time", 0.6),
    FactorResult("vehicle", 0.84),
    FactorResult("suspect_description", 0.9),
    FactorResult("weapon_tool", 0.2),
    FactorResult("target_profile", 1.0),
]


def test_strike_lowers_the_score_example():
    before = score_pair(BASE_FACTORS)
    after = strike(before, "weapon_tool")
    assert after.score < before.score
    struck = next(f for f in after.factors if f.factor == "weapon_tool")
    assert struck.struck_by_skeptic and struck.value == 0.2  # value kept for display


@pytest.mark.parametrize("name", [f.factor for f in BASE_FACTORS])
def test_strike_never_raises_the_score(name):
    """Even striking a below-average factor must not raise the score."""
    before = score_pair(BASE_FACTORS)
    assert strike(before, name).score <= before.score


def test_strike_never_raises_across_value_grid():
    grid = [0.0, 0.3, 0.7, 1.0]
    for va, vb, vc in itertools.product(grid, repeat=3):
        fs = [FactorResult("mo_similarity", va), FactorResult("vehicle", vb), FactorResult("target_profile", vc)]
        base = score_pair(fs)
        for f in fs:
            assert strike(base, f.factor).score <= base.score + 1e-9


# ----- H-MEM cap ------------------------------------------------------------

def test_memory_sum_capped_at_plus_minus_0_08():
    delta, applied = cap_memory([{"delta": 0.06, "memory_ids": ["HM-1"], "reason": "a"},
                                 {"delta": 0.05, "memory_ids": ["HM-2"], "reason": "b"}])
    assert delta == pytest.approx(0.08)
    assert [a["memory_id"] for a in applied] == ["HM-1", "HM-2"]
    assert applied[0]["effect"] == "+0.06"
    delta, _ = cap_memory([{"delta": -0.2}])
    assert delta == pytest.approx(-0.08)


def test_memory_applied_and_shown_on_score():
    fs = [FactorResult("mo_similarity", 0.6), FactorResult("space_time", 0.5)]
    plain = score_pair(fs)
    with_mem = score_pair(fs, memory=[{"delta": 0.03, "memory_ids": ["HM-9"], "reason": "approved red Pulsar pairs"}])
    assert with_mem.score == pytest.approx(plain.score + 0.03, abs=1e-4)
    assert with_mem.memory_applied[0]["text"] == "approved red Pulsar pairs"
    assert with_mem.memory_delta == pytest.approx(0.03)


def test_memory_can_drop_a_pair_below_the_alert_line():
    fs = [FactorResult("mo_similarity", 0.57)]
    assert score_pair(fs).alert is True
    assert score_pair(fs, memory=[{"delta": -0.05}]).alert is False


def test_score_clamped_to_unit_range():
    assert score_pair([FactorResult("mo_similarity", 1.0)], memory=[{"delta": 0.08}]).score == 1.0
    assert score_pair([FactorResult("mo_similarity", 0.0)], memory=[{"delta": -0.08}]).score == 0.0


# ----- forensic floor -------------------------------------------------------

def test_forensic_match_sets_floor_and_always_alerts():
    fs = [FactorResult("forensic", 1.0), FactorResult("mo_similarity", 0.0), FactorResult("space_time", 0.0)]
    p = score_pair(fs, memory=[{"delta": -0.08}])
    assert p.score == pytest.approx(0.8)
    assert p.alert is True and p.band == "high" and p.forensic_floor_applied is True


def test_forensic_floor_never_lowers_a_higher_score():
    p = score_pair([FactorResult("forensic", 1.0), FactorResult("mo_similarity", 0.95)])
    assert p.score > 0.8 and p.forensic_floor_applied is False


def test_struck_forensic_gives_no_floor():
    base = score_pair([FactorResult("forensic", 1.0), FactorResult("mo_similarity", 0.0)])
    assert strike(base, "forensic").score == 0.0


def test_forensic_mismatch_gives_no_floor():
    p = score_pair([FactorResult("forensic", 0.0), FactorResult("mo_similarity", 0.5)])
    assert p.score < 0.55 and p.alert is False


# ----- baseline -------------------------------------------------------------

A = {"crime_id": "A", "category": "robbery", "occurred_from": "2026-10-01T20:00:00+05:30",
     "location": {"lat": 13.0, "lon": 80.25}}


def test_baseline_links_same_category_close_in_space_and_time():
    b = {**A, "crime_id": "B", "occurred_from": "2026-10-10T20:00:00+05:30", "location": {"lat": 13.01, "lon": 80.25}}
    assert baseline_link(A, b) is True


def test_baseline_rejects_far_late_or_other_category():
    far = {**A, "crime_id": "B", "location": {"lat": 13.05, "lon": 80.25}}  # ~5.6 km
    late = {**A, "crime_id": "C", "occurred_from": "2026-10-20T20:00:00+05:30"}
    other = {**A, "crime_id": "D", "category": "burglary"}
    assert not baseline_link(A, far)
    assert not baseline_link(A, late)
    assert not baseline_link(A, other)
    assert not baseline_link(A, A)


# ----- R7: scoring is pure code ---------------------------------------------

SCORING_DIR = Path(__file__).resolve().parents[2] / "services" / "api" / "app" / "scoring"
FORBIDDEN_IMPORTS = ("httpx", "openai", "duckdb", "psycopg", "app.adapters", "adapters", "nightshift", "zetaris")


def test_scoring_imports_no_model_or_data_adapter():
    """Rule R7: scores are computed in code; nothing in app/scoring can call a model or Zetaris."""
    files = list(SCORING_DIR.glob("*.py"))
    assert files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for n in names:
                stripped = n.lstrip(".")
                assert not any(stripped == f or stripped.startswith(f + ".") or f in stripped.split(".")
                               for f in FORBIDDEN_IMPORTS), f"{path.name} imports {n}"
