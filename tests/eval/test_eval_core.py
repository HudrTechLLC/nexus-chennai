"""app.eval (WS2-14): metrics, truth loading, and an end-to-end run over a tiny planted city."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))
from agents_fixtures import ADYAR, HOUSEBREAK, VELACHERY, FakeNightshift, FakeZetaris, default_handlers  # noqa: E402

from app.agents import AgentDeps  # noqa: E402
from app.eval import Evaluator, Truth, load_truth, pair_metrics, series_purity  # noqa: E402
from app.eval.core import band_precision_note, key  # noqa: E402
from app.tracing import Tracer  # noqa: E402


def test_pair_metrics_excludes_duplicates():
    pos = {("A", "B"), ("C", "D")}
    m = pair_metrics([("A", "B"), ("A", "C"), ("E", "F")], pos, exclude={("E", "F")})
    assert m == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert pair_metrics([], set(), set())["precision"] is None


def test_series_purity():
    series = [{"series_id": "S1", "crime_ids": ["a", "b", "c"]}, {"series_id": "S2", "crime_ids": ["x", "y"]}]
    out = series_purity([("a", "b"), ("b", "c"), ("c", "x")], series)
    assert out == {"predicted_series": 1, "mean_purity": 0.75}


def test_load_truth(tmp_path):
    (tmp_path / "pairs.csv").write_text("crime_a,crime_b,label,group_id\nB,A,series,S1\nC,D,duplicate,D1\n"
                                        "E,F,decoy,X\n", encoding="utf-8")
    (tmp_path / "series.json").write_text(json.dumps([{"series_id": "S1", "crime_ids": ["A", "B", "G"]}]))
    t = load_truth(tmp_path)
    assert t.positives == {("A", "B")} and t.duplicates == {("C", "D")}
    assert t.crimes() == ["A", "B", "C", "D", "E", "F", "G"]


def test_evaluator_beats_baseline_on_planted_pair(tmp_path):
    """Hero pair: 2 days and ~4.4 km apart, so the rules-only baseline (<= 2 km) misses it; the agent finds it."""
    a, b, h = ADYAR["crime_id"], VELACHERY["crime_id"], HOUSEBREAK["crime_id"]
    truth = Truth({key(a, b): "series", key(a, h): "decoy"}, [{"series_id": "S1", "crime_ids": [a, b]}])
    tr = Tracer("e", tmp_path, echo=False)
    nightshift = FakeNightshift(lambda *x: (_ for _ in ()).throw(AssertionError("eval must not call a model")))
    deps = AgentDeps(tracer=tr, zetaris=FakeZetaris(default_handlers()), nightshift=nightshift)
    report = Evaluator(deps, truth).run([a, b, h])
    assert report["agent"]["tp"] == 1 and report["agent"]["fp"] == 0 and report["agent"]["recall"] == 1.0
    assert report["baseline_rules_only"]["tp"] == 0
    assert report["beats_baseline"]["recall"] is True
    assert report["agent"]["by_band"]["high"]["alerts"] == 1
    assert "correct 100%" in band_precision_note(report)["high"]
    assert report["synthetic"] is True and nightshift.calls == []
    assert any(c[1] == "Skeptic" for c in deps.zetaris.calls)  # strikes are part of what is measured
