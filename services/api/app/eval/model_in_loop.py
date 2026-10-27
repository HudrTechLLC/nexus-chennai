"""Model-in-the-loop side eval (task #21; engg/docs/eval/MODEL_IN_LOOP_PREREG.md).

The same 10 fixed cases in two arms, on the sample data (DuckDB twins), with nothing written anywhere shared:

- A, code only: `Evaluator.run(ids)`, unchanged (default plan -> code scoring -> Skeptic.check). 0 model calls.
- B, model in the loop: `AgentGraph(deps).run("case", ...)` per case, sequentially, against the live Nightshift:
  the model Planner (<= 3 rounds), Linker explanations, and the Skeptic's critique with send-backs (<= 2).

Both arms use engines=None (no H-MEM adjustment) and an in-memory store. Traces go to a temp folder.

    cd services/api
    SAMPLE_MODE=true NEXUS_STORE=memory METERLESS_RUNTIME_TOKEN_FILE=<Nightshift token path> \
      python -m app.eval.model_in_loop --out ../../output_examples/model_in_loop_eval.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT, Settings
from .core import key, load_truth, pair_metrics
from .planted_skeptic import _guard

CASE_IDS = [  # the first 10 of load_truth(data/sample/_truth).crimes(), fixed in the prereg
    "CHN-AD-2026-001071", "CHN-AD-2026-001078", "CHN-AD-2026-001084", "CHN-AD-2026-001182", "CHN-AM-2024-001346",
    "CHN-AM-2025-000865", "CHN-AM-2025-001042", "CHN-AM-2025-001062", "CHN-AS-2025-000080", "CHN-AV-2026-000609",
]
TRUTH_DIR = REPO_ROOT / "data" / "sample" / "_truth"
RECEIPT_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "ai.meterless.runtime" / "receipts.jsonl"


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def code_arm(settings: Settings, truth: Any, logs: Path, ids: list[str] | None = None) -> dict[str, Any]:
    from ..adapters.nightshift import NightshiftClient
    from ..adapters.zetaris import ZetarisClient
    from ..agents import AgentDeps
    from ..tracing import Tracer
    from .core import Evaluator

    tracer = Tracer("mil-code", logs, echo=False)
    z = ZetarisClient(settings, tracer)
    started = time.perf_counter()
    try:
        deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=NightshiftClient(settings, tracer), engines=None)
        report = Evaluator(deps, truth).run(list(ids or CASE_IDS))
    finally:
        z.close()
    calls = [e for e in tracer.read() if e["action"] == "model_call"]
    return {"agent": report["agent"], "model_calls": len(calls), "seconds": round(time.perf_counter() - started, 1)}


def model_case(settings: Settings, cid: str, logs: Path) -> dict[str, Any]:
    from ..adapters.nightshift import NightshiftClient
    from ..adapters.zetaris import ZetarisClient
    from ..agents import AgentDeps, MemoryStore
    from ..graph import AgentGraph
    from ..graph.runner import media_loader_for
    from ..tracing import Tracer

    tracer = Tracer(f"mil-{cid}", logs, echo=False)
    z = ZetarisClient(settings, tracer)
    n = NightshiftClient(settings, tracer, record_fixtures=False)
    started = time.perf_counter()
    out: dict[str, Any] = {"case_id": cid}
    try:
        deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=None, store=MemoryStore(),
                         deadline=time.monotonic() + settings.run_deadline_seconds)
        state = AgentGraph(deps, media_loader=media_loader_for(settings)).run("case", {"crime_id": cid})
        alerts = state.get("alerts") or []
        out.update(
            status=state.get("status"), errors=list(state.get("errors") or [])[:5],
            pairs=[{"pair": list(key(*a["crimes"][:2])), "score": a.get("score"), "band": a.get("band")}
                   for a in alerts if len(a.get("crimes") or []) >= 2],
            plan_rounds=state.get("plan_round", 0), send_backs=state.get("send_backs", 0),
            dropped=len(state.get("dropped") or []), approved=len(state.get("approved") or []),
            struck=sum(len((a.get("skeptic") or {}).get("struck") or []) for a in alerts),
        )
    except Exception as exc:  # a failed case is reported, not hidden
        out.update(status="failed", errors=[f"{type(exc).__name__}: {exc}"[:300]], pairs=[])
    finally:
        z.close()
        n.close()
    events = tracer.read()
    calls = [e for e in events if e["action"] == "model_call"]
    out["seconds"] = round(time.perf_counter() - started, 1)
    out["model_calls"] = {
        "total": len(calls),
        "by_status": dict(Counter(e.get("status") for e in calls)),
        "by_agent": dict(Counter(e.get("agent_name") for e in calls)),
        "by_model": dict(Counter(e.get("routed_model") or e.get("model") for e in calls)),
        "replayed": sum(e.get("status") == "replayed" for e in calls),
    }
    out["receipt_ids"] = sorted({e["receipt_id"] for e in calls if e.get("receipt_id")})
    out["deadline_hit"] = any(e.get("action") in ("skip_model_for_deadline", "deadline") for e in events)
    return out


def receipts(ids: list[str]) -> dict[str, Any]:
    if not RECEIPT_LOG.is_file():
        return {"checked": False, "reason": "no local Nightshift receipt log"}
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import verify_receipts as V  # noqa: E402

    log, _ = V.load_log(RECEIPT_LOG)
    return {"checked": True, **V.check_ids(ids, log)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "output_examples" / "model_in_loop_eval.json")
    ap.add_argument("--stop-at", type=float, default=None, help="epoch seconds: start no new case after this")
    args = ap.parse_args(argv)

    settings = Settings()
    _guard(settings)
    truth = load_truth(TRUTH_DIR)
    assert truth.crimes()[:10] == CASE_IDS, "case rule changed: the first 10 sample truth crimes differ"
    logs = Path(tempfile.mkdtemp(prefix="nexus-mil-"))
    report: dict[str, Any] = {"prereg": "engg/docs/eval/MODEL_IN_LOOP_PREREG.md", "code_sha": _git("rev-parse", "HEAD"),
                              "code_dirty": bool(_git("status", "--porcelain", "services/api")),
                              "cases": CASE_IDS, "synthetic": True, "sample_mode": settings.sample_mode,
                              "lanes": settings.lanes}

    report["code_only"] = code_arm(settings, truth, logs)
    print("code-only:", json.dumps(report["code_only"]["agent"]), flush=True)

    rows, unfinished = [], []
    for cid in CASE_IDS:
        if args.stop_at and time.time() > args.stop_at:
            unfinished.append(cid)
            continue
        r = model_case(settings, cid, logs)
        rows.append(r)
        print(cid, r["status"], f"{r['seconds']}s", "pairs", len(r["pairs"]), "calls", r["model_calls"]["total"],
              "replayed", r["model_calls"]["replayed"], flush=True)
        args.out.write_text(json.dumps({**report, "model_in_loop": {"cases": rows, "unfinished": CASE_IDS[len(rows):]}},
                                       indent=2) + "\n", encoding="utf-8")  # partial results survive a stop

    done = [r["case_id"] for r in rows]
    positives = {p for p in truth.positives if p[0] in done or p[1] in done}
    best: dict[tuple[str, str], float] = {}
    for r in rows:
        for p in r["pairs"]:
            k = tuple(p["pair"])
            best[k] = max(best.get(k, -1.0), p.get("score") or 0.0)
    live_cases = [r["case_id"] for r in rows if r["model_calls"]["replayed"] == 0 and r["status"] != "failed"]
    report["model_in_loop"] = {
        "cases": rows,
        "unfinished": unfinished,
        "partial": bool(unfinished),
        "metrics": pair_metrics(best, positives, truth.duplicates),
        "live_cases": live_cases,
        "totals": {
            "model_calls": sum(r["model_calls"]["total"] for r in rows),
            "replayed": sum(r["model_calls"]["replayed"] for r in rows),
            "send_backs": sum(r.get("send_backs", 0) for r in rows),
            "plan_rounds": sum(r.get("plan_rounds", 0) for r in rows),
            "dropped": sum(r.get("dropped", 0) for r in rows),
            "struck": sum(r.get("struck", 0) for r in rows),
            "seconds": round(sum(r["seconds"] for r in rows), 1),
            "deadline_hits": sum(bool(r.get("deadline_hit")) for r in rows),
        },
        "receipts": receipts([i for r in rows for i in r["receipt_ids"]]),
    }
    if unfinished:  # code-only on exactly the finished cases too, so both arms compare like for like
        report["code_only_on_finished"] = code_arm(settings, truth, logs, done)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("model-in-loop:", json.dumps(report["model_in_loop"]["metrics"]), json.dumps(report["model_in_loop"]["totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
