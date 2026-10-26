"""`python -m app.eval`: precision and recall versus the rules-only baseline (spec F3).

    python -m app.eval                      # data/generated/_truth if present, else data/sample/_truth
    python -m app.eval --truth data/sample/_truth --limit 200
    python -m app.eval --out output_examples/eval_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.zetaris import ZetarisClient
from ..agents import AgentDeps
from ..config import REPO_ROOT, get_settings
from ..tracing import Tracer, new_run_id
from .core import Evaluator, band_precision_note, load_truth


def default_truth() -> Path:
    for p in (REPO_ROOT / "data" / "generated" / "_truth", REPO_ROOT / "data" / "sample" / "_truth"):
        if (p / "pairs.csv").exists():
            return p
    raise SystemExit("No ground truth found (data/generated/_truth or data/sample/_truth). "
                     "Run `python -m data.generator --seed 42` first.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate linking against planted ground truth (F3)")
    ap.add_argument("--truth", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N truth crimes")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "output_examples" / "eval_report.json")
    args = ap.parse_args()

    truth_dir = args.truth or default_truth()
    truth = load_truth(truth_dir)
    s = get_settings()
    run_id = new_run_id("eval")
    tracer = Tracer(run_id, s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    try:
        with engines.use_tracer(tracer):
            deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=NightshiftClient(s, tracer), engines=None)
            crimes = truth.crimes()[: args.limit] if args.limit else truth.crimes()
            report = Evaluator(deps, truth).run(crimes)
    finally:
        z.close()
    report["truth_dir"] = str(truth_dir.relative_to(REPO_ROOT)) if truth_dir.is_relative_to(REPO_ROOT) else str(
        truth_dir)
    report["sample_mode"] = s.sample_mode
    report["run_id"] = run_id
    report["log_file"] = f"logs/trace-{run_id}.jsonl"
    report["band_accuracy_text"] = band_precision_note(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    a, b = report["agent"], report["baseline_rules_only"]
    print(f"agent    precision={a['precision']} recall={a['recall']} alerts={a['alerts']}")
    print(f"baseline precision={b['precision']} recall={b['recall']} alerts={b['alerts']}")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
