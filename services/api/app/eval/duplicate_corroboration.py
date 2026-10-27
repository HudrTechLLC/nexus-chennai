"""Duplicate and derivative corroboration: an offline measurement (task #18).

Pre-registered in engg/docs/eval/DUPLICATE_CORROBORATION_PREREG.md. It re-runs the headline eval's flow
(`Evaluator.evaluate_case`: the default plan, Linker scoring, the Skeptic's code check, approved alerts only) on
the 60 truth cases, and keeps each alert's factor rows. For each alert's `corroboration` items it marks:
- **derivative**: a news article (NEWS-<crime_id>), 112 call (calls.crime_id) or tip (source_row_id) whose own
  source crime is one of the pair's two crimes;
- **duplicate**: a second counted item with the same normalised text.
It then recomputes the corroboration factor without those items and re-scores the pair with the same
`score_pair`, to count the alerts that would lose a band. No scoring or eval code is changed.

Run: `cd services/api && SAMPLE_MODE=true python -m app.eval.duplicate_corroboration`
"""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb

from .. import engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.zetaris import ZetarisClient
from ..agents import AgentDeps, Candidate
from ..agents.planner import Plan, default_plan
from ..config import REPO_ROOT, get_settings
from ..scoring import factors as F
from ..scoring.combine import FactorResult, score_pair
from ..tracing import Tracer, new_run_id
from .core import Evaluator, key, load_truth

SAMPLE = REPO_ROOT / "data" / "sample"
OUT = REPO_ROOT / "engg" / "docs" / "eval" / "duplicate_corroboration_results.json"
BAND_RANK = {"high": 2, "medium": 1, None: 0}


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())).strip()


def load_sources() -> dict[tuple[str, str], dict[str, Any]]:
    """(view, row id) -> {"source_crime": ..., "text": ...} for every corroboration source row."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    with open(SAMPLE / "news" / "articles.jsonl", encoding="utf-8") as f:
        for line in f:
            a = json.loads(line)
            aid = a["article_id"]
            out[("v_news_mentions", aid)] = {
                "source_crime": aid[len("NEWS-"):] if aid.startswith("NEWS-") else None,
                "text": _norm(f"{a.get('headline', '')} {a.get('body', '')}")}
    con = duckdb.connect()
    for cid, crime in con.execute(f"SELECT call_id, crime_id FROM '{(SAMPLE / 'calls' / 'calls.parquet').as_posix()}'"
                                  ).fetchall():
        out[("v_calls_near_crime", cid)] = {"source_crime": crime, "text": None}  # calls carry no free text
    for tid, text, src in con.execute(f"SELECT tip_id, text, source_row_id FROM "
                                      f"'{(SAMPLE / 'sb' / 'tips.parquet').as_posix()}'").fetchall():
        out[("v_tip_corroboration", tid)] = {"source_crime": src, "text": _norm(text) or None}
    return out


def classify(evidence: list[dict[str, Any]], pair: tuple[str, str], sources: dict) -> list[dict[str, Any]]:
    """Each counted item with its kind: independent, derivative or duplicate (first text occurrence counts)."""
    seen: set[str] = set()
    rows = []
    for ev in evidence:
        view, rid = ev.get("view"), str(ev.get("row"))
        src = sources.get((view, rid), {})
        kind = "independent"
        if src.get("source_crime") in pair:
            kind = "derivative"
        elif src.get("text") and src["text"] in seen:
            kind = "duplicate"
        if src.get("text"):
            seen.add(src["text"])
        rows.append({"view": view, "id": rid, "source_crime": src.get("source_crime"), "kind": kind,
                     "known": bool(src)})
    return rows


def rescored(score, keep: int, pair: tuple[str, str]):
    """The pair re-scored with corroboration counted from `keep` independent items (None when 0)."""
    value = F.corroboration([{"crime_ids": list(pair)}] * keep, *pair) if keep else None
    fs = [FactorResult(f.factor, value if f.factor == "corroboration" else f.value, f.weight, f.evidence,
                       f.struck_by_skeptic, f.reason) for f in score.factors]
    return score_pair(fs)


def collect(ev: Evaluator, crime_ids: list[str]) -> dict[tuple[str, str], Any]:
    """The eval's approved alerts (best score per pair, as Evaluator.run), keeping each pair's PairScore."""
    cache: dict[str, tuple] = {}
    best: dict[tuple[str, str], Any] = {}
    for cid in crime_ids:
        if cid not in cache:
            cache[cid] = ev._case(cid)
        case, feats = cache[cid]
        if case is None:
            continue
        support = ev.planner.execute(Plan(default_plan(case, feats), 1, "default"))
        cand_rows = (support.get("q_candidates") or {}).get("rows") or []
        ev._prefetch((r.get("crime_id") for r in cand_rows if r.get("crime_id") and r.get("crime_id") != cid),
                     cache)
        cands = []
        for r in cand_rows:
            b = r.get("crime_id")
            if not b or b == cid:
                continue
            if b not in cache:
                cache[b] = ev._case(b)
            crime_b, feats_b = cache[b]
            if crime_b is not None:
                cands.append(Candidate(crime_b, feats_b))
        for sp in ev.linker.score(case, feats, cands, support):
            if not sp.score.alert:
                continue
            if ev.skeptic.check(sp).verdict != "approve":
                continue
            k = key(*sp.crimes)
            if k not in best or sp.score.score > best[k].score:
                best[k] = sp.score
    return best


def measure(best: dict[tuple[str, str], Any], sources: dict) -> dict[str, Any]:
    alerts = []
    for pair, score in sorted(best.items()):
        corr = next((f for f in score.factors if f.factor == "corroboration"), None)
        items = classify(corr.evidence if corr and corr.value is not None else [], pair, sources)
        keep = sum(i["kind"] == "independent" for i in items)
        after = rescored(score, keep, pair) if items else score
        alerts.append({"pair": list(pair), "band": score.band, "score": score.score,
                       "items": items, "independent": keep,
                       "band_after": after.band if after.alert else None, "score_after": after.score})
    n = len(alerts)
    with_corr = [a for a in alerts if a["items"]]
    any_dd = [a for a in with_corr if any(i["kind"] != "independent" for i in a["items"])]
    all_dd = [a for a in with_corr if all(i["kind"] != "independent" for i in a["items"])]
    lose = [a for a in alerts if BAND_RANK[a["band_after"]] < BAND_RANK[a["band"]]]
    kinds: dict[str, int] = {}
    for a in with_corr:
        for i in a["items"]:
            kinds[f"{i['view']}:{i['kind']}"] = kinds.get(f"{i['view']}:{i['kind']}", 0) + 1
    return {
        "synthetic": True,
        "alerts": n,
        "a_with_corroboration": len(with_corr),
        "b_with_duplicate_or_derivative": len(any_dd),
        "c_all_duplicate_or_derivative": len(all_dd),
        "d_lose_a_band": {"alerts": len(lose), "share": round(len(lose) / n, 4) if n else None,
                          "high_to_medium": sum(a["band"] == "high" and a["band_after"] == "medium" for a in lose),
                          "medium_to_none": sum(a["band"] == "medium" and a["band_after"] is None for a in lose)},
        "items_by_view_and_kind": dict(sorted(kinds.items())),
        "unknown_items": sum(not i["known"] for a in with_corr for i in a["items"]),
        "alerts_detail": alerts,
    }


def main() -> None:
    s = get_settings()
    if not s.sample_mode:
        raise SystemExit("Run with SAMPLE_MODE=true (offline, headline eval conditions).")
    truth = load_truth(SAMPLE / "_truth")
    tracer = Tracer(new_run_id(), s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    try:
        with engines.use_tracer(tracer):
            deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=NightshiftClient(s, tracer), engines=None)
            best = collect(Evaluator(deps, truth), truth.crimes())
    finally:
        z.close()
    res = measure(best, load_sources())
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "alerts_detail"}, indent=1))


if __name__ == "__main__":
    main()
