"""Nemotron-alone baseline: the reason-lane model judges candidate pairs with no Nexus scoring.

Pre-registered in engg/docs/eval/NEMOTRON_ALONE_PREREG.md. Two steps, run from services/api:

    SAMPLE_MODE=true python -m app.eval.nemotron_alone select   # writes the committed case + pair list
    SAMPLE_MODE=true METERLESS_RUNTIME_TOKEN_FILE=<path> python -m app.eval.nemotron_alone run --out ...

`select` makes no model calls: it reruns the headline evaluator (sample data, no Zetaris key) and checks
that it reproduces the headline's TP/FP/FN before it writes anything. `run` reads ONLY the committed list
and the committed prompt; it never re-derives pairs, never writes Supabase, and refuses replayed output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT

PREREG_DIR = REPO_ROOT / "engg" / "docs" / "eval" / "nemotron_alone"
CASES_PATH = PREREG_DIR / "cases.json"
PROMPT_PATH = PREREG_DIR / "prompt.json"
HEADLINE_REPORT = REPO_ROOT / "output_examples" / "eval_report.json"
TRUTH_DIR = REPO_ROOT / "data" / "sample" / "_truth"

CASE_EVERY = 3        # cases: every 3rd headline case in sorted order (index 0, 3, ..., 57 of 60)
PAIRS_PER_CASE = 10   # pairs: each case's first 10 candidates in the blocker's own order (km_apart, crime_id)
MAX_CONSECUTIVE_FAILURES = 3

# Fields shown to the model, per crime. Everything else (crime_id, fir_no, station_id, source ids, h3/geohash,
# extractor receipts, any score) stays out: no identifier, no Nexus output, no truth.
CRIME_FIELDS = ("category", "sub_type", "occurred_from", "occurred_to", "address", "weapon", "offenders_described",
                "victims", "vehicles", "property", "narrative")
FEATURE_FIELDS = ("mo", "visual_tags", "entities")


# =====================
# Helpers
# =====================

def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def truth_hashes(truth_dir: Path = TRUTH_DIR) -> dict[str, str]:
    return {p.name: sha256(p) for p in sorted(truth_dir.iterdir()) if p.is_file()}


def km_between(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    try:
        la1, lo1, la2, lo2 = (math.radians(float(x)) for x in (a["lat"], a["lon"], b["lat"], b["lon"]))
    except (KeyError, TypeError, ValueError):
        return None
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371.0088 * math.asin(math.sqrt(h)), 2)


def hours_between(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    try:
        ta = datetime.fromisoformat(str(a["occurred_from"]))
        tb = datetime.fromisoformat(str(b["occurred_from"]))
    except (KeyError, TypeError, ValueError):
        return None
    return round(abs((tb - ta).total_seconds()) / 3600, 1)


def crime_evidence(crime: dict[str, Any], features: dict[str, Any] | None) -> dict[str, Any]:
    out = {k: crime.get(k) for k in CRIME_FIELDS}
    out["witness_statements"] = [s.get("text") for s in (crime.get("statements") or []) if s.get("text")]
    feats = features or crime.get("features")
    out["extracted_features"] = {k: feats.get(k) for k in FEATURE_FIELDS} if feats else None
    return out


def pair_evidence(a: tuple[dict, dict | None], b: tuple[dict, dict | None]) -> dict[str, Any]:
    return {"crime_A": crime_evidence(*a), "crime_B": crime_evidence(*b),
            "distance_km": km_between(a[0], b[0]), "hours_between_start_times": hours_between(a[0], b[0])}


def blind_terms(truth_dir: Path = TRUTH_DIR) -> set[str]:
    """Strings that would leak the answer: every crime id, truth group id, series id and series name."""
    import csv

    terms: set[str] = set()
    with (truth_dir / "pairs.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            terms.update(x for x in (r.get("crime_a"), r.get("crime_b"), r.get("group_id")) if x)
    series_path = truth_dir / "series.json"
    if series_path.exists():
        for s in json.loads(series_path.read_text(encoding="utf-8")):
            terms.update(str(s[k]) for k in ("series_id", "name") if s.get(k))
    return terms


def assert_blind(text: str, terms: set[str], crime_ids: tuple[str, ...] = ()) -> None:
    """The prompt payload must carry no truth key, label, group/series id or name, and no crime id."""
    for bad in ("_truth", "series_id", "group_id", "\"label\"", "is_series", "same_offender"):
        if bad in text:
            raise AssertionError(f"prompt is not blind: contains {bad!r}")
    for t in set(terms) | set(crime_ids):
        if t and t in text:
            raise AssertionError(f"prompt is not blind: contains {t!r}")
    if re.search(r"\b(SER|DEC|DUP)-[A-Z0-9-]+", text):
        raise AssertionError("prompt is not blind: contains a truth group id")


def load_prompt(path: Path = PROMPT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_messages(prompt: dict[str, Any], evidence: dict[str, Any]) -> list[dict[str, str]]:
    body = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    return [{"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user_template"].replace("{evidence}", body)}]


def parse_verdict(obj: dict[str, Any]) -> tuple[bool, float | None]:
    """Pre-registered: link is the model's boolean `link` (confidence reported, never thresholded)."""
    link = obj.get("link")
    if not isinstance(link, bool):
        raise ValueError(f"`link` is not a boolean: {link!r}")
    conf = obj.get("confidence")
    try:
        conf = None if conf is None else max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf = None
    return link, conf


def score(pairs: list[tuple[str, str]], predicted: set[tuple[str, str]], positives: set[tuple[str, str]],
          duplicates: set[tuple[str, str]]) -> dict[str, Any]:
    """Pair metrics on exactly `pairs` (the headline's pair_metrics; duplicate pairs excluded as in the headline)."""
    from .core import pair_metrics

    in_set = set(pairs)
    return pair_metrics(predicted & in_set, positives & in_set, duplicates)


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sample_deps(run_name: str, transport=None):
    from ..adapters.nightshift import NightshiftClient
    from ..adapters.zetaris import ZetarisClient
    from ..agents import AgentDeps
    from ..config import get_settings
    from ..tracing import Tracer

    s = get_settings()
    if not s.sample_mode or s.zetaris_api_key:
        raise SystemExit("Run with SAMPLE_MODE=true and no Zetaris key: the baseline uses the headline's sample data.")
    tracer = Tracer(run_name, s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    return s, tracer, z, AgentDeps(tracer=tracer, zetaris=z, nightshift=NightshiftClient(s, tracer, transport=transport),
                                         engines=None)


# =====================
# select (no model calls)
# =====================

def select(out: Path = CASES_PATH) -> dict[str, Any]:
    from .. import engines
    from ..agents.planner import Plan
    from .core import Evaluator, default_plan, load_truth, pair_metrics

    truth = load_truth(TRUTH_DIR)
    crimes = truth.crimes()
    _, tracer, z, deps = _sample_deps("nemotron_alone_select")
    links: set[tuple[str, str]] = set()
    chosen = crimes[::CASE_EVERY]
    ranked: dict[str, list[str]] = {}
    with engines.use_tracer(tracer):
        ev = Evaluator(deps, truth)
        cache: dict[str, tuple] = {}
        for cid in crimes:  # the system's decisions: exactly the headline loop, all 60 cases
            preds, _, _ = ev.evaluate_case(cid, cache)
            links.update(p.pair for p in preds)
        for cid in chosen:  # each chosen case's candidates in the blocker's own order
            case, feats = cache[cid]
            support = ev.planner.execute(Plan(default_plan(case, feats), 1, "default"))
            rows = (support.get("q_candidates") or {}).get("rows") or []
            ids = [r["crime_id"] for r in rows if r.get("crime_id") and r["crime_id"] != cid]
            ranked[cid] = [b for b in ids if cache.get(b, (None,))[0] is not None][:PAIRS_PER_CASE]
    z.close()

    head = json.loads(HEADLINE_REPORT.read_text(encoding="utf-8"))
    got = pair_metrics(links, truth.positives, truth.duplicates)
    want = {k: head["agent"][k] for k in ("tp", "fp", "fn")}
    if {k: got[k] for k in want} != want or len(links) != head["agent"]["alerts"]:
        raise SystemExit(f"Does not reproduce the headline: {got} alerts={len(links)} vs {want} "
                         f"alerts={head['agent']['alerts']}. Not writing a pair list.")

    pairs, seen = [], set()
    for cid in chosen:
        for rank, b in enumerate(ranked[cid], 1):
            k = pair_key(cid, b)
            if k in seen:
                continue
            seen.add(k)
            pairs.append({"pair": f"{k[0]}|{k[1]}", "case": cid, "rank": rank, "system_linked": k in links})
    doc = {
        "prereg": "engg/docs/eval/NEMOTRON_ALONE_PREREG.md",
        "headline": {"report": "output_examples/eval_report.json", "git_commit": head["provenance"]["git_commit"],
                     "run_id": head["run_id"], **want, "alerts": head["agent"]["alerts"],
                     "reproduced": True},
        "generated_at_commit": _git_head(),
        "truth_dir": "data/sample/_truth",
        "truth_sha256": truth_hashes(),
        "rule": {"cases": f"every {CASE_EVERY}rd of the {len(crimes)} headline cases in sorted order "
                          f"(indices 0, {CASE_EVERY}, ..., {CASE_EVERY * (len(chosen) - 1)})",
                 "pairs_per_case": PAIRS_PER_CASE,
                 "pair_order": "q_candidates order (km_apart, crime_id), crimes missing from q_cases skipped "
                               "as the evaluator skips them; a pair reached from two cases is listed once",
                 "system_linked": "pair is in the headline evaluator's alert set over all 60 cases "
                                  "(linker alert and skeptic approve)"},
        "cases": chosen,
        "pairs": pairs,
        # The system's whole alert set touching the chosen cases (any candidate rank, not only the 10 nearest),
        # for the second recall line: what blocking plus scoring reach beyond the pairs the model is shown.
        "system_alerts_touching_cases": sorted(f"{a}|{b}" for a, b in links if a in chosen or b in chosen),
    }
    _dump(out, doc)
    return doc


# =====================
# run (model calls; after nexus-3's planted test only)
# =====================

def run(out: Path, stop_at: datetime | None = None, transport=None) -> dict[str, Any]:
    from .. import engines
    from ..agents.base import AgentError, chat_json, reason_budget
    from .core import Evaluator, load_truth

    plan = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    prompt = load_prompt()
    if plan["truth_sha256"] != truth_hashes():
        raise SystemExit("data/sample/_truth differs from the pre-registered hashes. Not running.")
    s, tracer, z, deps = _sample_deps("nemotron_alone", transport)
    model = deps.nightshift.model_for(prompt["lane"])
    if model != prompt["model"]:
        raise SystemExit(f"Lane {prompt['lane']} is pinned to {model}, not the pre-registered {prompt['model']}.")
    if not (s.meterless_runtime_token or "").strip():
        raise SystemExit("No Nightshift runtime token: sample mode would replay fixtures, not call the model.")
    truth = load_truth(TRUTH_DIR)
    terms = blind_terms()

    done: dict[str, dict[str, Any]] = {}
    if out.exists():  # resume: completed cases are reused verbatim
        prev = json.loads(out.read_text(encoding="utf-8"))
        done = {r["pair"]: r for r in prev.get("pairs", [])}
    by_case: dict[str, list[dict[str, Any]]] = {}
    for p in plan["pairs"]:
        by_case.setdefault(p["case"], []).append(p)

    results = dict(done)
    completed = [c for c in plan["cases"] if all(p["pair"] in done for p in by_case.get(c, []))]
    stopped = None
    fails = 0
    with engines.use_tracer(tracer):
        ev = Evaluator(deps, truth)
        cache: dict[str, tuple] = {}
        for cid in plan["cases"]:
            if cid in completed:
                continue
            if stop_at and datetime.now(timezone.utc) >= stop_at:
                stopped = "stop time reached"
                break
            for p in by_case.get(cid, []):
                a, b = p["pair"].split("|")
                for x in (a, b):
                    if x not in cache:
                        cache[x] = ev._case(x)
                evidence = pair_evidence(cache[a], cache[b])
                msgs = build_messages(prompt, evidence)
                assert_blind(msgs[1]["content"], terms, (a, b))
                row: dict[str, Any] = {"pair": p["pair"], "case": cid, "system_linked": p["system_linked"]}
                t0 = time.perf_counter()
                try:
                    obj, res = chat_json(deps, prompt["lane"], msgs, agent="NemotronAlone", purpose=p["pair"],
                                         expect="link", temperature=prompt["temperature"],
                                         max_tokens=reason_budget(1))
                    if getattr(res, "replayed", False):
                        raise AgentError("replayed output refused")
                    link, conf = parse_verdict(obj)
                    row.update(status="ok", model_link=link, confidence=conf, reason=str(obj.get("reason", ""))[:400],
                               routed_model=res.routed_model, receipt_id=res.receipt_id)
                    fails = 0
                except (AgentError, ValueError) as exc:
                    row.update(status="failed", model_link=False, confidence=None, error=str(exc)[:300])
                    fails += 1
                row["seconds"] = round(time.perf_counter() - t0, 1)
                results[p["pair"]] = row
                if fails >= MAX_CONSECUTIVE_FAILURES:
                    stopped = f"{fails} consecutive failed calls"
                    break
            if stopped:
                break
            completed.append(cid)
            _write(out, plan, prompt, results, completed, truth, None)
    z.close()
    return _write(out, plan, prompt, results, completed, truth, stopped)


def _write(out: Path, plan: dict, prompt: dict, results: dict, completed: list[str], truth, stopped) -> dict:
    keep = [p for p in plan["pairs"] if p["case"] in completed]
    rows = [results[p["pair"]] for p in keep]
    pairs = [pair_key(*p["pair"].split("|")) for p in keep]
    model_links = {pair_key(*r["pair"].split("|")) for r in rows if r["model_link"]}
    sys_links = {pair_key(*p["pair"].split("|")) for p in keep if p["system_linked"]}
    reach = {k for k in truth.positives if k[0] in completed or k[1] in completed} - truth.duplicates
    sys_all = {pair_key(*x.split("|")) for x in plan["system_alerts_touching_cases"]}
    doc = {
        "prereg": plan["prereg"], "cases_file_commit": plan["generated_at_commit"],
        "headline": plan["headline"], "model": prompt["model"], "lane": prompt["lane"],
        "temperature": prompt["temperature"], "code_commit": _git_head(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stopped_early": stopped,
        "cases_completed": len(completed), "cases_planned": len(plan["cases"]),
        "pairs_scored": len(keep),
        "failed_calls": sum(1 for r in rows if r["status"] == "failed"),
        "metrics_on_pair_set": {"nemotron_alone": score(pairs, model_links, truth.positives, truth.duplicates),
                                "full_system": score(pairs, sys_links, truth.positives, truth.duplicates)},
        "recall_vs_all_positives_of_completed_cases": {
            "positives": len(reach),
            "nemotron_alone": len(model_links & reach), "full_system": len(sys_all & reach),
            "note": "full_system counts its whole headline alert set (any candidate rank); the model saw only "
                    "the 10 nearest candidates per case"},
        "supabase_writes": 0,
        "pairs": rows,
    }
    _dump(out, doc)
    return doc


def _dump(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:  # LF on every OS, so files compare byte for byte
        fh.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.eval.nemotron_alone")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select", help="write the pre-registered case and pair list (no model calls)")
    r = sub.add_parser("run", help="call the model on the committed pairs")
    r.add_argument("--out", type=Path, default=REPO_ROOT / "output_examples" / "nemotron_alone.json")
    r.add_argument("--stop-at", help="ISO time; no new case starts after it (completed cases only are scored)")
    a = ap.parse_args(argv)
    if a.cmd == "select":
        doc = select()
        print(f"{len(doc['cases'])} cases, {len(doc['pairs'])} pairs, "
              f"{sum(p['system_linked'] for p in doc['pairs'])} system links -> {CASES_PATH}")
    else:
        stop = datetime.fromisoformat(a.stop_at) if a.stop_at else None
        if stop is not None and stop.tzinfo is None:
            raise SystemExit("--stop-at needs a UTC offset, e.g. 2026-10-27T09:30:00+05:30")
        doc = run(a.out, stop)
        print(json.dumps({k: doc[k] for k in ("cases_completed", "pairs_scored", "failed_calls", "stopped_early",
                                               "metrics_on_pair_set")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
