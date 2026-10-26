"""Alert writer (spec E3, D3.11, F1 step 8). Code only, no model. Task WS2-13.

Turns Skeptic-approved pairs into `LinkAlert` records (validated against app.models),
writes them through the store, and queues a notification for each station involved.
Only factors that had data are written: `link_factors.value` and `reason` are NOT NULL.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from ..models import LinkAlert
from ..tracing import IST
from .base import AgentDeps, short
from .linker import fallback_reason
from .skeptic import SkepticResult

AGENT = "Alert writer"


def alert_id_for(crimes: Sequence[str], year: int) -> str:
    """Stable id per crime pair: re-running the same case updates the same alert."""
    h = int(hashlib.sha1("|".join(sorted(crimes)).encode("utf-8")).hexdigest()[:10], 16) % 1_000_000
    return f"LA-{year}-{h:06d}"


def build_alert(res: SkepticResult, run_id: str, now: datetime | None = None) -> LinkAlert:
    sp = res.pair
    ps = sp.score
    now = now or datetime.now(IST)
    factors = []
    for f in ps.factors:
        if f.value is None:
            continue
        factors.append({
            "factor": f.factor,
            "weight": f.weight,
            "value": round(f.value, 4),
            "evidence": [{"view": e["view"], "row": e["row"]} for e in f.evidence],
            "reason": f.reason or fallback_reason(f),
            "struck_by_skeptic": f.struck_by_skeptic,
        })
    stations = list(dict.fromkeys(s for s in (sp.crime_a.get("station_id"), sp.crime_b.get("station_id")) if s))
    rationale = sp.rationale or (
        f"Linked by code score {ps.score} ({ps.band}) over {ps.factors_with_data} factors; "
        "model rationale unavailable."
    )
    return LinkAlert(
        alert_id=alert_id_for(sp.crimes, now.year),
        kind="pair",
        crimes=sp.crimes,
        stations=stations,
        score=ps.score,
        band=ps.band,
        factors=factors,
        memory_applied=[{"memory_id": m["memory_id"] or "HM-unknown", "effect": m["effect"], "text": m["text"]}
                        for m in ps.memory_applied],
        skeptic=res.review_block(),
        rationale=rationale,
        recommended_action=sp.recommended_action,
        status="pending",
        run_id=run_id,
        created_at=now,
    )


class AlertWriter:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def write(self, results: Sequence[SkepticResult]) -> list[dict[str, Any]]:
        written: list[dict[str, Any]] = []
        for res in results:
            if res.verdict != "approve" or not res.pair.score.alert or res.pair.score.band is None:
                continue
            alert = build_alert(res, self.deps.tracer.run_id)
            row = alert.model_dump(mode="json")
            # Full evidence refs incl. query + query_id (G2); the model validated view/row.
            full = {f.factor: f.evidence for f in res.pair.score.factors}
            for f in row["factors"]:
                f["evidence"] = full.get(f["factor"], f["evidence"])
            row["synthetic"] = bool(res.pair.crime_a.get("synthetic", True) or res.pair.crime_b.get("synthetic", True))
            row["coverage"] = res.pair.score.coverage
            stored = self.deps.store.write_alert(row)
            self.deps.store.notify([
                {"station_id": st, "kind": "link_alert", "title": f"New {alert.band} link alert {alert.alert_id}",
                 "body": alert.rationale, "link": f"/console/alerts/{alert.alert_id}"}
                for st in alert.stations
            ])
            written.append(stored)
            self.deps.tracer.emit(AGENT, "write_alert", input_summary=res.pair.pair_id,
                                  output_summary=short(f"{alert.alert_id} {alert.band} {alert.score} "
                                                       f"stations={alert.stations}"),
                                  confidence=alert.score, status="ok")
        return written
