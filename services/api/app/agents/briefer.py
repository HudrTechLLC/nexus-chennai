"""Briefer agent (spec E3: `tiny`, falling back to `fast`). Task WS2-20.

Writes a zone briefing from the day's alerts and analyst decisions. Every number comes from
code (`briefing_facts`). The model only turns the facts into prose, and any number in its
text that is not among the facts rejects the draft in favour of a code-written one (R7).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .base import AgentDeps, AgentError, chat_json, short

AGENT = "Briefer"

BRIEFER_PROMPT = """You write a short morning briefing for police officers in one zone.
Use ONLY the facts given; do not invent or recompute numbers. 4-6 plain sentences: what is new,
what needs a decision, what was rejected and why, and one suggested focus for today.
Return ONE JSON object: {"briefing": str}. Output it once, then stop."""


def briefing_facts(zone: str, day: str, alerts: Sequence[Mapping[str, Any]],
                   decisions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hot = [a for a in alerts if a.get("kind") == "hotspot" and a.get("status", "pending") == "pending"]
    alerts = [a for a in alerts if a.get("kind", "pair") != "hotspot"]
    new = [a for a in alerts if a.get("status", "pending") == "pending"]
    cross = [a for a in new if len(set(a.get("stations") or [])) > 1]
    bands = Counter(a.get("band") for a in new)
    reasons = Counter(d.get("reason_code") for d in decisions if d.get("decision") == "reject")
    stations = Counter(s for a in new for s in a.get("stations") or [])
    top = sorted(new, key=lambda a: a.get("score") or 0, reverse=True)[:3]
    return {
        "zone": zone,
        "day": day,
        "new_alerts": len(new),
        "high": bands.get("high", 0),
        "medium": bands.get("medium", 0),
        "cross_station": len(cross),
        "approved": sum(1 for d in decisions if d.get("decision") == "approve"),
        "rejected": sum(1 for d in decisions if d.get("decision") == "reject"),
        "rejection_reasons": dict(reasons.most_common(3)),
        "hotspots": len(hot),
        "hotspot_notes": [h.get("rationale") for h in hot[:2]],
        "busiest_stations": [s for s, _ in stations.most_common(3)],
        "top_alerts": [{"alert_id": a.get("alert_id"), "band": a.get("band"), "rationale": a.get("rationale")}
                       for a in top],
    }


def _numbers(v: Any) -> set[str]:
    if isinstance(v, bool):
        return set()
    if isinstance(v, (int, float)):
        return {str(int(v)) if float(v).is_integer() else str(v)}
    if isinstance(v, Mapping):
        return set().union(*(_numbers(x) for x in v.values()), *(_numbers(k) for k in v.keys())) if v else set()
    if isinstance(v, (list, tuple)):
        return set().union(*(_numbers(x) for x in v)) if v else set()
    if isinstance(v, str):
        return set(re.findall(r"\d+", v))
    return set()


def template_briefing(f: Mapping[str, Any]) -> str:
    s = (f"{f['zone']}, {f['day']}: {f['new_alerts']} new link alerts ({f['high']} high, {f['medium']} medium), "
         f"{f['cross_station']} across stations. Analysts approved {f['approved']} and rejected {f['rejected']}.")
    if f["rejection_reasons"]:
        s += " Main rejection reasons: " + ", ".join(str(k).replace("_", " ") for k in f["rejection_reasons"]) + "."
    if f.get("hotspots"):
        s += f" {f['hotspots']} hotspot(s) flagged."
    if f["top_alerts"]:
        s += f" Start with {f['top_alerts'][0]['alert_id']}."
    return s


class Briefer:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def _lane(self) -> str:
        try:
            self.deps.nightshift.model_for("tiny")
            return "tiny"
        except Exception:
            return "fast"  # E2 fallback

    def brief(self, zone: str, day: str, alerts: Sequence[Mapping[str, Any]],
              decisions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        facts = briefing_facts(zone, day, alerts, decisions)
        lane = self._lane()
        messages = [{"role": "system", "content": BRIEFER_PROMPT}, {"role": "user", "content": short(facts, 6000)}]
        model, source = None, "model"
        try:
            out, result = chat_json(self.deps, lane, messages, agent=AGENT, purpose=f"briefing {zone} {day}",
                                    temperature=0.3, thinking=False)
            text = str(out.get("briefing") or "").strip()
            extra = _numbers(text) - _numbers(facts)
            if not text or extra:
                raise AgentError(f"briefing rejected: numbers not in facts {sorted(extra)[:5]}")
            model = result.model
        except AgentError as exc:
            text, source = template_briefing(facts), "template"
            self.deps.tracer.emit(AGENT, "briefing_fallback", output_summary=short(str(exc)), status="degraded")
        self.deps.tracer.emit(AGENT, "brief", input_summary=f"{zone} {day}", output_summary=short(text), model=model,
                              status="ok" if source == "model" else "degraded")
        return {"zone": zone, "day": day, "text": text, "facts": facts, "lane": lane, "model": model,
                "source": source}
