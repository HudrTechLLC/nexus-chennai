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


def eval_handlers():
    """default_handlers plus q_cases, which the evaluator uses to prefetch candidates in batches."""
    h = default_handlers()
    h["q_cases"] = lambda p: [h["q_case"]({"crime_id": v})[0] for _, v in sorted(p.items())
                              if v and h["q_case"]({"crime_id": v})]
    return h


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
    deps = AgentDeps(tracer=tr, zetaris=FakeZetaris(eval_handlers()), nightshift=nightshift)
    report = Evaluator(deps, truth).run([a, b, h])
    assert report["agent"]["tp"] == 1 and report["agent"]["fp"] == 0 and report["agent"]["recall"] == 1.0
    assert report["baseline_rules_only"]["tp"] == 0
    assert report["beats_baseline"]["recall"] is True
    assert report["agent"]["by_band"]["high"]["alerts"] == 1
    assert "correct 100%" in band_precision_note(report)["high"]
    assert report["synthetic"] is True and nightshift.calls == []
    assert any(c[1] == "Skeptic" for c in deps.zetaris.calls)  # strikes are part of what is measured


def test_evaluator_excludes_non_generated_crimes(tmp_path):
    """A console-filed FIR copying a planted MO must not count as a false positive (nexus-5)."""
    a, b, h = ADYAR["crime_id"], VELACHERY["crime_id"], HOUSEBREAK["crime_id"]
    truth = Truth({key(a, h): "decoy"}, [])  # truth knows nothing about VELACHERY: treat it as the console FIR
    deps = AgentDeps(tracer=Tracer("e", tmp_path, echo=False), zetaris=FakeZetaris(eval_handlers()),
                     nightshift=FakeNightshift(lambda *x: "{}"))
    with_fir = Evaluator(deps, truth).run([a, h])
    assert with_fir["agent"]["fp"] == 1  # the a<->b link would be a false positive
    clean = Evaluator(deps, truth, exclude={b}).run([a, b, h])
    assert clean["agent"]["fp"] == 0 and clean["cases_evaluated"] == 2
    assert clean["excluded_non_generated"] == [b]
    assert clean["features"]["with_live_model_features"] + len(clean["features"]["without_features"]) \
        + len(clean["features"]["features_without_receipt"]) == 2


def test_non_generated_ids_uses_generator_namespace(monkeypatch):
    import uuid

    from app.eval import __main__ as cli

    gen = "CHN-AD-2026-001182"
    rows = [{"crime_id": gen, "source_row_id": str(uuid.uuid5(cli.GEN_NS, gen))},
            {"crime_id": "CHN-AD-2026-001231", "source_row_id": str(uuid.uuid4())}]

    class SB:
        configured = True

        def __init__(self, s):
            pass

        def select(self, table, params):
            return rows

        def close(self):
            pass

    monkeypatch.setattr(cli, "SupabaseClient", SB)
    assert cli.non_generated_ids(None) == ["CHN-AD-2026-001231"]
    seed = (Path(__file__).resolve().parents[2] / "data" / "seed.py").read_text(encoding="utf-8")
    assert str(cli.GEN_NS) in seed  # one namespace: the generator's (data/seed.py GEN_NS)


def test_candidates_are_prefetched_in_batches_not_one_by_one(tmp_path):
    """Live each q_case + q_features costs ~2.4 s; candidates come in one q_cases + one q_features call."""
    a, b, h = ADYAR["crime_id"], VELACHERY["crime_id"], HOUSEBREAK["crime_id"]
    truth = Truth({key(a, b): "series"}, [{"series_id": "S1", "crime_ids": [a, b]}])
    deps = AgentDeps(tracer=Tracer("e", tmp_path, echo=False), zetaris=FakeZetaris(eval_handlers()),
                     nightshift=FakeNightshift(lambda *x: "{}"))
    Evaluator(deps, truth).run([a])
    evals = [c for c in deps.zetaris.calls if c[1] == "Eval"]
    assert [c[0] for c in evals].count("q_case") == 1  # the case itself
    assert [c[0] for c in evals].count("q_cases") == 1  # both candidates in one call
    assert {b, h} <= set(next(c[2] for c in evals if c[0] == "q_cases").values())
