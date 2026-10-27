"""Classification and re-scoring used by the duplicate/derivative corroboration measurement (task #18)."""

from __future__ import annotations

from app.eval import duplicate_corroboration as D
from app.scoring.combine import FactorResult, score_pair

PAIR = ("CHN-A-1", "CHN-B-2")
SOURCES = {
    ("v_calls_near_crime", "C1"): {"source_crime": "CHN-A-1", "text": None},  # the call that reported crime A
    ("v_calls_near_crime", "C2"): {"source_crime": "CHN-X-9", "text": None},
    ("v_tip_corroboration", "T1"): {"source_crime": None, "text": "red pulsar two men"},
    ("v_tip_corroboration", "T2"): {"source_crime": None, "text": "red pulsar two men"},
}


def test_classify_marks_derivative_and_duplicate():
    ev = [{"view": v, "row": r} for v, r in SOURCES]
    kinds = [i["kind"] for i in D.classify(ev, PAIR, SOURCES)]
    assert kinds == ["derivative", "independent", "independent", "duplicate"]


def test_rescore_drops_factor_when_nothing_independent_is_left():
    fs = [FactorResult("mo_similarity", 0.9), FactorResult("space_time", 0.8), FactorResult("vehicle", 0.7),
          FactorResult("corroboration", 0.39)]
    before = score_pair(fs)
    after = D.rescored(before, 0, PAIR)
    assert next(f for f in after.factors if f.factor == "corroboration").value is None
    assert after.score > before.score  # removing a low corroboration value can raise the score
