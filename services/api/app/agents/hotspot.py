"""Hotspot detector (spec E3, LNK-05): unusual concentration of crime in a hex cell and time window.

Statistical, no model (rule R7: every number here is computed in code). Owner: nexus-2.

    from app.agents.hotspot import detect_hotspots
    hotspots = detect_hotspots(deps, since="2026-10-19", until="2026-10-26")

Reads only the named query `q_hex_counts` (rule R1): per (h3 cell, category, day) the number of
crimes, their ids and stations, from `baseline_since` to `until`.

Method, per (cell, category):
- observed  = crimes in the window [since, until);
- baseline  = crimes in the BASELINE_WINDOWS windows of the same length before `since`;
- prior     = the category's citywide average per active cell per window (empirical-Bayes shrinkage,
              so a cell with little history is not judged on one quiet month);
- expected  = (baseline + PRIOR_WEIGHT * prior) / (BASELINE_WINDOWS + PRIOR_WEIGHT), floored at MIN_EXPECTED;
- p         = P(X >= observed) for X ~ Poisson(expected);
- band      = high when p < 0.01 and observed >= 5; medium when p < 0.05 and observed >= 3; else nothing.
- score     = 1 - p, rounded to 3 decimals.
Returned dicts follow D3.11 (kind "hotspot"); the graph runner adds alert_id and run_id.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

AGENT = "Hotspot detector"
BASELINE_WINDOWS = 8
PRIOR_WEIGHT = 2.0
MIN_EXPECTED = 0.25
BANDS = (("high", 0.01, 5), ("medium", 0.05, 3))
# Hex-day rows over 9 windows can pass the adapter's default 1000-row cap; ask for all of them.
ROW_LIMIT = 200_000


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam), computed stably in log space."""
    if k <= 0:
        return 1.0
    term = math.exp(-lam)  # P(X = 0)
    cdf = term
    for i in range(1, k):
        term *= lam / i
        cdf += term
    return max(0.0, 1.0 - cdf)


def _day(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _ids(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = json.loads(v) if v[:1] == "[" else [x for x in v.split(",") if x]
    return [str(x) for x in v]


def detect_hotspots(deps: Any, *, since: str, until: str, cells: list[str] | None = None) -> list[dict]:
    start, end = _day(since), _day(until)
    length = (end - start).days
    if length <= 0:
        raise ValueError("until must be after since")
    baseline_since = start - timedelta(days=length * BASELINE_WINDOWS)
    rows, qid = deps.query("q_hex_counts", agent=AGENT, limit=ROW_LIMIT, since=start.isoformat(),
                           until=end.isoformat(), baseline_since=baseline_since.isoformat())

    observed: dict[tuple[str, str], int] = defaultdict(int)
    baseline: dict[tuple[str, str], int] = defaultdict(int)
    crimes: dict[tuple[str, str], list[str]] = defaultdict(list)
    stations: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rows:
        key = (str(r["cell"]), str(r["category"]))
        d, n = _day(r["day"]), int(r["n"])
        if start <= d < end:
            observed[key] += n
            crimes[key] += _ids(r.get("crime_ids"))
            stations[key] |= set(_ids(r.get("station_ids")))
        elif baseline_since <= d < start:
            baseline[key] += n

    # Citywide prior per category: average baseline count per active cell per window.
    cat_total: dict[str, int] = defaultdict(int)
    cat_cells: dict[str, set[str]] = defaultdict(set)
    for (cell, cat), n in baseline.items():
        cat_total[cat] += n
        cat_cells[cat].add(cell)
    for cell, cat in observed:
        cat_cells[cat].add(cell)

    wanted = set(cells) if cells else None
    out: list[dict] = []
    for key, obs in observed.items():
        cell, cat = key
        if wanted is not None and cell not in wanted:
            continue
        prior = cat_total[cat] / (max(1, len(cat_cells[cat])) * BASELINE_WINDOWS)
        expected = max(MIN_EXPECTED, (baseline[key] + PRIOR_WEIGHT * prior) / (BASELINE_WINDOWS + PRIOR_WEIGHT))
        p = poisson_sf(obs, expected)
        band = next((b for b, p_max, n_min in BANDS if p < p_max and obs >= n_min), None)
        if band is None:
            continue
        out.append({
            "kind": "hotspot",
            "crimes": sorted(set(crimes[key])),
            "stations": sorted(stations[key]),
            "score": round(1 - p, 3),
            "band": band,
            "rationale": (f"{obs} {cat.replace('_', ' ')} crimes in cell {cell} from {start} to {end} "
                          f"vs {expected:.1f} expected from the previous {BASELINE_WINDOWS} windows "
                          f"(Poisson p={p:.2g})."),
            "status": "pending",
            "factors": [],
            "cell": cell,
            "category": cat,
            "window": {"since": start.isoformat(), "until": end.isoformat()},
            "observed": obs,
            "expected": round(expected, 3),
            "p_value": p,
            "zetaris_query_ids": [qid],
        })
    out.sort(key=lambda h: (h["p_value"], h["cell"], h["category"]))
    deps.tracer.emit(AGENT, "detect_hotspots", input_summary=f"{start}..{end}, {len(rows)} hex-day rows",
                     output_summary=f"{len(out)} hotspots ({sum(h['band'] == 'high' for h in out)} high)",
                     zetaris_query_ids=[qid], status="ok")
    return out
