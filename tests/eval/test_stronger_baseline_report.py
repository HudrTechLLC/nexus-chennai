"""eval_report.json carries the pre-registered stronger baseline as a NEW key; the headline keys are unchanged."""

from __future__ import annotations

import json

from app.config import REPO_ROOT
from app.eval.core import stronger_baseline

REPORT = json.loads((REPO_ROOT / "output_examples" / "eval_report.json").read_text(encoding="utf-8"))


def test_report_has_the_new_key_next_to_an_unchanged_headline():
    b = REPORT["baseline_rules_plus_vehicle"]
    assert b["prereg"] == "engg/docs/eval/STRONGER_BASELINE_PREREG.md"
    assert {"tp", "fp", "fn", "precision", "recall", "f1", "alerts", "rule", "strict"} <= set(b)
    assert {"tp", "fp", "fn", "precision", "recall", "f1", "alerts", "rule"} <= set(b["strict"])
    # the headline and the rules-only baseline stay exactly as published
    assert (REPORT["agent"]["precision"], REPORT["agent"]["recall"]) == (0.5915, 0.8571)
    assert (REPORT["baseline_rules_only"]["precision"], REPORT["baseline_rules_only"]["recall"]) == (0.0866, 0.2959)
    assert REPORT["baseline_rules_only"]["rule"] == "same category, <= 2 km, <= 14 days"


def test_stronger_baseline_block_uses_the_headline_pair_metrics():
    pos, dups = {("a", "b"), ("c", "d")}, {("x", "y")}
    out = stronger_baseline({"primary": {("a", "b"), ("e", "f"), ("x", "y")}, "strict": {("a", "b")}}, pos, dups, 10)
    assert (out["tp"], out["fp"], out["fn"], out["alerts"]) == (1, 1, 1, 3)  # the duplicate is excluded, not an fp
    assert out["strict"]["precision"] == 1.0 and out["strict"]["recall"] == 0.5
    assert out["false_alerts_per_100_cases"] == 10.0
