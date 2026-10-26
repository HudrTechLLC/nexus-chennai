"""`python -m app.eval`: precision and recall versus the rules-only baseline (spec F3).

    python -m app.eval                      # data/generated/_truth if present, else data/sample/_truth
    python -m app.eval --truth data/sample/_truth --limit 200
    python -m app.eval --out output_examples/eval_report.json
    python -m app.eval --mo-cosine both    # D-027 trial: report precision/recall with the flag off and on

Reproducible by construction: no model calls (R7) and no H-MEM (the evaluator has no engines, so no
memory adjusts a score; analysts' live decisions cannot leak in). Crimes not made by the generator
(console-filed FIRs: source_row_id != uuid5(GEN_NS, crime_id), see data/seed.py) are excluded.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from .. import engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.zetaris import ZetarisClient
from ..agents import AgentDeps
from ..adapters.supabase import SupabaseClient
from ..config import REPO_ROOT, get_settings
from ..tracing import Tracer, new_run_id
from .core import Evaluator, band_precision_note, load_truth


def default_truth() -> Path:
    for p in (REPO_ROOT / "data" / "generated" / "_truth", REPO_ROOT / "data" / "sample" / "_truth"):
        if (p / "pairs.csv").exists():
            return p
    raise SystemExit("No ground truth found (data/generated/_truth or data/sample/_truth). "
                     "Run `python -m data.generator --seed 42` first.")


GEN_NS = uuid.UUID("6f1c2a52-6a71-4c51-9e57-2c7b1b0a0e42")  # same value as data/seed.py GEN_NS (generator)
MO_COSINE_FLAG = "NEXUS_MO_COSINE"


def non_generated_ids(settings) -> list[str]:
    """Crimes in Supabase not made by the generator (console FIRs); [] when Supabase is not configured."""
    sb = SupabaseClient(settings)
    if not sb.configured:
        return []
    out: list[str] = []
    offset = 0
    try:
        while True:
            rows = sb.select("crimes", {"select": "crime_id,source_row_id", "order": "crime_id.asc",
                                        "limit": "1000", "offset": str(offset)})
            out += [r["crime_id"] for r in rows if r.get("source_row_id") != str(uuid.uuid5(GEN_NS, r["crime_id"]))]
            if len(rows) < 1000:
                return out
            offset += 1000
    finally:
        sb.close()


def evaluate(truth, crimes, exclude, s, run_id):
    tracer = Tracer(run_id, s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    try:
        with engines.use_tracer(tracer):
            deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=NightshiftClient(s, tracer), engines=None)
            return Evaluator(deps, truth, exclude=exclude).run(crimes)
    finally:
        z.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate linking against planted ground truth (F3)")
    ap.add_argument("--truth", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N truth crimes")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "output_examples" / "eval_report.json")
    ap.add_argument("--mo-cosine", choices=("off", "on", "both"), default="off",
                    help="engines.similarity.mo_cosine in mo_similarity (NEXUS_MO_COSINE); 'both' runs twice")
    ap.add_argument("--exclude-file", type=Path, help="extra crime ids to exclude, one per line")
    args = ap.parse_args()

    truth_dir = args.truth or default_truth()
    truth = load_truth(truth_dir)
    s = get_settings()
    run_id = new_run_id("eval")
    crimes = truth.crimes()[: args.limit] if args.limit else truth.crimes()
    exclude = set(non_generated_ids(s))
    if args.exclude_file:
        exclude |= {ln.strip() for ln in args.exclude_file.read_text(encoding="utf-8").splitlines() if ln.strip()}
    modes = ["off", "on"] if args.mo_cosine == "both" else [args.mo_cosine]
    previous = os.environ.get(MO_COSINE_FLAG)
    reports = {}
    try:
        for mode in modes:
            os.environ[MO_COSINE_FLAG] = "1" if mode == "on" else ""
            reports[mode] = evaluate(truth, crimes, exclude, s, run_id if mode == modes[0] else f"{run_id}-{mode}")
    finally:
        if previous is None:
            os.environ.pop(MO_COSINE_FLAG, None)
        else:
            os.environ[MO_COSINE_FLAG] = previous
    report = reports[modes[0]]
    report["mo_cosine"] = modes[0]
    if len(modes) == 2:
        report["mo_cosine_trial"] = {m: {k: r["agent"][k] for k in ("precision", "recall", "tp", "fp", "fn", "alerts")
                                         if k in r["agent"]} for m, r in reports.items()}
    report["hmem"] = "off: no memory adjusts any score (reproducible; live analyst decisions excluded)"
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
