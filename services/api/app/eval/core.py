"""Linking evaluation against planted ground truth (spec F3, LNK-10). Task WS2-14.

What is measured: the code that produces alerts, i.e. blocking (q_candidates) -> F2 scoring
(Linker.score) -> Skeptic re-query and strikes (Skeptic.check). The reason lane only explains
links and cannot change a number (R7), so the eval makes no model calls and is
reproducible. Support queries follow the Planner's deterministic default plan.

Baseline (F3): rules only, the same category, <= 2 km and <= 14 days, over the same
candidate pairs.

Ground truth is read from `_truth/` (pairs.csv and series.json) here and nowhere else in the app.
- Positive labels: series, vehicle_chain, offender_return.
- Negative: decoy, and any pair not listed.
- `duplicate` pairs (the same incident at two stations) are excluded from precision and recall
  and reported separately as dedup.
"""

from __future__ import annotations

import csv
import json
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agents import AgentDeps, Candidate, Linker, Skeptic
from ..agents.base import crime_from_row, features_from_row
from ..agents.planner import Planner, default_plan
from ..scoring import WEIGHTS_VERSION, baseline_link

POSITIVE_LABELS = frozenset({"series", "vehicle_chain", "offender_return"})
FEATURE_BATCH = 100  # crime ids per q_features call when prefetching candidates


def key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


@dataclass
class Truth:
    labels: dict[tuple[str, str], str]
    series: list[dict[str, Any]]

    @property
    def positives(self) -> set[tuple[str, str]]:
        return {k for k, v in self.labels.items() if v in POSITIVE_LABELS}

    @property
    def duplicates(self) -> set[tuple[str, str]]:
        return {k for k, v in self.labels.items() if v == "duplicate"}

    def crimes(self) -> list[str]:
        ids = {c for pair in self.labels for c in pair}
        for s in self.series:
            ids.update(s.get("crime_ids") or [])
        return sorted(ids)


def load_truth(truth_dir: Path) -> Truth:
    labels: dict[tuple[str, str], str] = {}
    with (truth_dir / "pairs.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            labels[key(row["crime_a"], row["crime_b"])] = row["label"].strip()
    series_path = truth_dir / "series.json"
    series = json.loads(series_path.read_text(encoding="utf-8")) if series_path.exists() else []
    return Truth(labels, series)


@dataclass
class Predicted:
    pair: tuple[str, str]
    score: float
    band: str | None
    category: str | None
    struck: list[str] = field(default_factory=list)


def pair_metrics(predicted: Iterable[tuple[str, str]], positives: set[tuple[str, str]],
                 exclude: set[tuple[str, str]]) -> dict[str, Any]:
    pred = {p for p in predicted if p not in exclude}
    tp = len(pred & positives)
    fp = len(pred - positives)
    fn = len(positives - pred)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    r = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "precision": r(precision), "recall": r(recall), "f1": r(f1)}


def components(edges: Iterable[tuple[str, str]]) -> list[set[str]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[str, set[str]] = defaultdict(set)
    for x in parent:
        groups[find(x)].add(x)
    return list(groups.values())


def series_purity(edges: Iterable[tuple[str, str]], series: list[dict[str, Any]]) -> dict[str, Any]:
    """Purity of predicted groups of 3+ cases: share of the group from its dominant true series."""
    member = {cid: s["series_id"] for s in series for cid in s.get("crime_ids") or []}
    groups = [g for g in components(edges) if len(g) >= 3]
    purities = []
    for g in groups:
        counts: dict[str, int] = defaultdict(int)
        for cid in g:
            counts[member.get(cid, "_none")] += 1
        best = max((v for k, v in counts.items() if k != "_none"), default=0)
        purities.append(best / len(g))
    return {"predicted_series": len(groups),
            "mean_purity": round(statistics.mean(purities), 4) if purities else None}


class Evaluator:
    def __init__(self, deps: AgentDeps, truth: Truth, exclude: Iterable[str] = ()) -> None:
        self.deps = deps
        self.truth = truth
        # Crimes outside the generated dataset (console-filed FIRs): truth knows nothing about them, so a
        # link to one would count as a false positive. They are skipped as cases and as candidates.
        self.exclude = set(exclude)
        self.linker = Linker(deps)
        self.skeptic = Skeptic(deps)
        self.planner = Planner(deps)

    def _case(self, cid: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        rows, _ = self.deps.query("q_case", agent="Eval", crime_id=cid)
        if not rows:
            return None, None
        frows, _ = self.deps.query("q_features", agent="Eval", ids=cid)
        return crime_from_row(rows[0]), (features_from_row(frows[0]) if frows else None)

    def _prefetch(self, ids: Iterable[str], cache: dict[str, tuple]) -> None:
        """Fill the cache for many crimes in a few round trips: q_cases (25 per call) and q_features (100 per
        call), instead of q_case + q_features per candidate (about 2.4 s each live). Same rows, same parsing
        as _case; a crime missing from q_cases is cached as (None, None), as _case would."""
        todo = [i for i in dict.fromkeys(ids) if i and i not in cache]
        if not todo:
            return
        from ..adapters.zetaris_queries_n2 import cases_params

        cases: dict[str, dict[str, Any]] = {}
        for params in cases_params(todo):
            rows, _ = self.deps.query("q_cases", agent="Eval", **params)
            cases.update({r["crime_id"]: r for r in rows})
        feats: dict[str, dict[str, Any]] = {}
        have = [i for i in todo if i in cases]
        for start in range(0, len(have), FEATURE_BATCH):
            rows, _ = self.deps.query("q_features", agent="Eval", ids=",".join(have[start:start + FEATURE_BATCH]))
            for r in rows:
                feats.setdefault(r["crime_id"], r)
        for i in todo:
            row = cases.get(i)
            cache[i] = ((crime_from_row(row), features_from_row(feats[i]) if i in feats else None)
                        if row is not None else (None, None))

    def evaluate_case(self, cid: str, cache: dict[str, tuple]) -> tuple[list[Predicted], list[tuple[str, str]], float]:
        started = time.perf_counter()
        if cid not in cache:
            cache[cid] = self._case(cid)
        case, feats = cache[cid]
        if case is None:
            return [], [], 0.0
        from ..agents.planner import Plan
        support = self.planner.execute(Plan(default_plan(case, feats), 1, "default"))
        cand_rows = (support.get("q_candidates") or {}).get("rows") or []
        self._prefetch((r.get("crime_id") for r in cand_rows
                        if r.get("crime_id") and r.get("crime_id") != cid and r.get("crime_id") not in self.exclude),
                       cache)
        cands = []
        for r in cand_rows:
            b = r.get("crime_id")
            if not b or b == cid or b in self.exclude:
                continue
            if b not in cache:
                cache[b] = self._case(b)
            crime_b, feats_b = cache[b]
            if crime_b is not None:
                cands.append(Candidate(crime_b, feats_b))
        baseline = [key(cid, c.crime["crime_id"]) for c in cands if baseline_link(case, c.crime)]
        pairs = self.linker.score(case, feats, cands, support)
        preds = []
        for sp in pairs:
            if not sp.score.alert:
                continue
            res = self.skeptic.check(sp)
            if res.verdict == "approve":
                preds.append(Predicted(key(*sp.crimes), sp.score.score, sp.score.band, case.get("category"),
                                       res.struck))
        return preds, baseline, time.perf_counter() - started

    def run(self, crime_ids: list[str]) -> dict[str, Any]:
        cache: dict[str, tuple] = {}
        best: dict[tuple[str, str], Predicted] = {}
        baseline: set[tuple[str, str]] = set()
        times = []
        crime_ids = [c for c in crime_ids if c not in self.exclude]
        for cid in crime_ids:
            preds, base, secs = self.evaluate_case(cid, cache)
            times.append(secs)
            baseline.update(base)
            for p in preds:
                if p.pair not in best or p.score > best[p.pair].score:
                    best[p.pair] = p
        evaluated = set(crime_ids)
        positives = {p for p in self.truth.positives if p[0] in evaluated or p[1] in evaluated}
        dups = self.truth.duplicates
        agent = pair_metrics(best, positives, dups)
        base = pair_metrics(baseline, positives, dups)
        by_band = {}
        for band in ("high", "medium"):
            sel = [k for k, p in best.items() if p.band == band]
            m = pair_metrics(sel, positives, dups)
            by_band[band] = {"alerts": len(sel), "precision": m["precision"], "tp": m["tp"], "fp": m["fp"]}
        by_type: dict[str, list] = defaultdict(list)
        for k, p in best.items():
            by_type[p.category or "unknown"].append(k)
        type_pos: dict[str, set] = defaultdict(set)
        cat = {cid: (cache.get(cid) or (None,))[0] for cid in evaluated}
        for a, b in positives:
            c = (cat.get(a) or cat.get(b) or {}).get("category") if (cat.get(a) or cat.get(b)) else None
            type_pos[c or "unknown"].add((a, b))
        by_crime_type = {t: pair_metrics(ks, type_pos.get(t, set()), dups) for t, ks in sorted(by_type.items())}
        false_alerts = agent["fp"]
        feats_by_case = {c: (cache.get(c) or (None, None))[1] for c in crime_ids}
        live = sorted(c for c, f in feats_by_case.items() if f and f.get("model") and f.get("receipt_id"))
        return {
            "synthetic": True,
            "weights_version": WEIGHTS_VERSION,
            "method": "blocking (q_candidates, default plan) -> F2 code scoring -> Skeptic re-query/strike; "
                      "no model calls (models only explain, R7)",
            "cases_evaluated": len(crime_ids),
            "features": {  # chief: live-model features vs fallback, per case
                "with_live_model_features": len(live),
                "without_features": sorted(c for c, f in feats_by_case.items() if not f),
                "features_without_receipt": sorted(c for c, f in feats_by_case.items()
                                                   if f and not (f.get("model") and f.get("receipt_id"))),
            },
            "excluded_non_generated": sorted(self.exclude),
            "truth_positive_pairs": len(positives),
            "agent": {**agent, "alerts": len(best), "by_band": by_band, "by_crime_type": by_crime_type,
                      "false_alerts_per_100_cases": round(100 * false_alerts / max(1, len(crime_ids)), 2),
                      "skeptic_strikes": sum(1 for p in best.values() if p.struck),
                      "series": series_purity([k for k in best if k in positives or k not in dups],
                                              self.truth.series)},
            "baseline_rules_only": {**base, "alerts": len(baseline),
                                    "rule": "same category, <= 2 km, <= 14 days",
                                    "false_alerts_per_100_cases": round(100 * base["fp"] / max(1, len(crime_ids)),
                                                                        2)},
            "duplicates": {"truth_pairs": len(dups), "flagged_by_agent": len(set(best) & dups),
                           "flagged_by_baseline": len(baseline & dups)},
            "timing": {"median_seconds_per_case": round(statistics.median(times), 3) if times else None},
            "beats_baseline": {
                "precision": _gt(agent["precision"], base["precision"]),
                "recall": _gt(agent["recall"], base["recall"]),
            },
        }


def _gt(a: float | None, b: float | None) -> bool | None:
    if a is None or b is None:
        return None
    return a > b


def band_precision_note(report: Mapping[str, Any]) -> dict[str, str]:
    """The F2 'weighted accuracy' sentence shown on alert cards, from the measured band precision."""
    out = {}
    for band, m in report["agent"]["by_band"].items():
        if m["precision"] is not None:
            out[band] = (f"alerts in the {band} band were correct {round(100 * m['precision'])}% of the time "
                         f"on the evaluation set ({m['alerts']} alerts)")
    return out
