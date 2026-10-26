"""Sanitiser agent (spec E3, D3.13, G1, J). Task WS2-19.

Drafts a public appeal from a case. The draft is never published here: an officer must
approve and publish it (`approved_by`, `published_at` are set by the publish step).

1. Code builds the allowed facts. Excluded: crime_id, FIR number, station, exact address,
   exact time, plates, names, phones, property values, victims and protected attributes.
   Place becomes an area label plus an H3 r8 cell, time becomes an ISO week and a time band.
2. The `fast` lane writes title, summary and looking_for from those facts only.
3. Code checks the text for leaks (digits that look like plates, phones or FIR numbers,
   clock times, the exact address, any id). A leaking draft falls back to a code template,
   and the trace says so.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ..scoring.factors import SUSPECT_ALLOWED_KEYS, parse_ts, time_band
from .base import AgentDeps, AgentError, chat_json, short

AGENT = "Sanitiser"
PUBLIC_H3_RES = 8

SANITISER_PROMPT = """You write short public appeals for information about a crime, for a city police website.
Use ONLY the facts given. Never add names, exact addresses, exact times, vehicle numbers, phone numbers,
case numbers, police station names, victim details, or religion/caste/community.
Return ONE JSON object: {"title": str (<= 70 chars), "summary": str (1-2 sentences),
"looking_for": [str] (2-4 short items the public could help with)}. Output it once, then stop."""

# Same list as public.appeal_text_leaks (0006_02) and apps/web/lib/appeals.ts; shared fixture
# tests/agents/appeal_leaks.json. Clock times are allowed: D3.13's own example asks for CCTV
# "between 7:30 and 8:00 pm".
_LEAKS = (
    re.compile(r"(^|[^A-Za-z0-9])[A-Z]{2} ?[0-9]{1,2} ?[A-Z?]{0,3} ?[0-9]{3,4}([^0-9]|$)"),  # plates
    re.compile(r"(^|[^A-Za-z])(CHN|PS)-[A-Z0-9-]+"),  # internal ids
    re.compile(r"(^|[^0-9])[0-9]{1,5}/[0-9]{4}([^0-9]|$)"),  # FIR numbers
    re.compile(r"[0-9]{6,}"),  # phones, long numbers
)
LEAK_KINDS = ("plate", "internal id", "FIR number", "phone or long number")


def leak_kind(text: str) -> str | None:
    """The first leak kind in `text`, or None (mirrors public.appeal_text_leaks)."""
    for kind, p in zip(LEAK_KINDS, _LEAKS):
        if p.search(text or ""):
            return kind
    return None



def area_label(case: Mapping[str, Any]) -> str:
    """'Adyar (LB Road area)': station locality + the road, never a house or landmark."""
    st = str(case.get("station_id") or "")
    parts = st.split("-")
    locality = parts[1].title() if len(parts) > 1 else "City"
    addr = str((case.get("location") or {}).get("address") or "")
    road = re.split(r"\s+(?:near|opp\.?|opposite|behind|next to)\s+", addr, maxsplit=1, flags=re.I)[0].strip()
    road = re.sub(r"^\d+[\w/-]*,?\s*", "", road)  # drop door numbers
    if road and len(road) <= 40 and not any(p.search(road) for p in _LEAKS):
        return f"{locality} ({road} area)"
    return locality


def public_cell(case: Mapping[str, Any]) -> str | None:
    loc = case.get("location") or {}
    if loc.get("lat") is None or loc.get("lon") is None:
        return None
    import h3
    return h3.latlng_to_cell(float(loc["lat"]), float(loc["lon"]), PUBLIC_H3_RES)


def iso_week(ts: datetime) -> str:
    y, w, _ = ts.isocalendar()
    return f"{y}-W{w:02d}"


def allowed_facts(case: Mapping[str, Any], features: Mapping[str, Any] | None) -> dict[str, Any]:
    ts = parse_ts(case.get("occurred_from"))
    vehicles = [{k: v.get(k) for k in ("type", "colour", "make_model") if v.get(k)}
                for v in case.get("vehicles") or [] if v.get("role", "used_by_offender") == "used_by_offender"]
    described = [{k: d.get(k) for k in SUSPECT_ALLOWED_KEYS if d.get(k) is not None}
                 for d in case.get("offenders_described") or []]
    mo = (features or {}).get("mo") or {}
    return {
        "category": case.get("sub_type") or case.get("category"),
        "area": area_label(case),
        "time_window": time_band(ts).title() if ts else None,
        "week": iso_week(ts) if ts else None,
        "vehicles": [v for v in vehicles if v],
        "offenders_described": [d for d in described if d],
        "property_types": sorted({str(p.get("type")) for p in case.get("property") or [] if p.get("type")}),
        "mo": {k: mo.get(k) for k in ("approach", "target", "escape", "place_type") if mo.get(k)},
        "visual_tags": list((features or {}).get("visual_tags") or [])[:6],
    }


def leaks(text: str, case: Mapping[str, Any]) -> list[str]:
    found = [p.pattern for p in _LEAKS if p.search(text)]
    addr = str((case.get("location") or {}).get("address") or "").strip()
    if addr and addr.lower() in text.lower():
        found.append("exact address")
    for key in ("crime_id", "fir_no", "station_id"):
        v = case.get(key)
        if v and str(v).lower() in text.lower():
            found.append(key)
    return found


def template_draft(facts: Mapping[str, Any]) -> dict[str, Any]:
    cat = str(facts.get("category") or "crime").replace("_", " ")
    veh = facts["vehicles"][0] if facts.get("vehicles") else {}
    veh_s = " ".join(str(veh[k]) for k in ("colour", "make_model", "type") if veh.get(k))
    looking = []
    if veh_s:
        looking.append(f"Sightings of a {veh_s}")
    if facts.get("time_window"):
        looking.append(f"Shop or home CCTV in the {facts['area']} during the {str(facts['time_window']).lower()}")
    looking.append("Anyone who saw something unusual nearby")
    return {"title": f"{cat.capitalize()} in {facts['area']}"[:70],
            "summary": f"A {cat} was reported in {facts['area']} in the {str(facts.get('time_window') or '').lower()}"
                       f"{' involving a ' + veh_s if veh_s else ''}.",
            "looking_for": looking}


class Sanitiser:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def draft(self, case: Mapping[str, Any], features: Mapping[str, Any] | None = None,
              public_incident_id: str | None = None) -> dict[str, Any]:
        facts = allowed_facts(case, features)
        if not facts["week"] or public_cell(case) is None:
            raise AgentError("case has no time or location; a public appeal needs both")
        messages = [{"role": "system", "content": SANITISER_PROMPT},
                    {"role": "user", "content": short(facts, 4000)}]
        model, source = None, "model"
        try:
            out, result = chat_json(self.deps, "fast", messages, agent=AGENT, purpose="public appeal", temperature=0.3,
                                    thinking=False)
            model = result.model
            text = {"title": str(out.get("title") or "")[:70], "summary": str(out.get("summary") or "")[:400],
                    "looking_for": [str(x)[:120] for x in (out.get("looking_for") or [])][:4]}
            bad = leaks(" ".join([text["title"], text["summary"], *text["looking_for"]]), case)
            if bad or not text["title"] or not text["summary"]:
                raise AgentError(f"draft rejected: {bad or 'empty'}")
        except AgentError as exc:
            text, source, model = template_draft(facts), "template", None
            self.deps.tracer.emit(AGENT, "draft_fallback", output_summary=short(str(exc)), status="degraded")
        digest = hashlib.sha1(str(case.get("crime_id")).encode("utf-8")).hexdigest()[:6].upper()
        pid = public_incident_id or f"PI-{facts['week'][:4]}-{digest}"  # stable, and reveals no case id
        draft = {
            "public_incident_id": pid,
            **text,
            "category": case.get("category"),
            "area_label": facts["area"],
            "cell": public_cell(case),
            "week": facts["week"],
            "time_window": facts["time_window"],
            "images": [],
            "sanitiser_model": model or "code-template",
            "approved_by": None,
            "published_at": None,
            "status": "draft",
            "source": source,
        }
        self.deps.tracer.emit(AGENT, "draft_appeal", input_summary=pid, output_summary=short(draft["title"]),
                              model=model, status="ok" if source == "model" else "degraded")
        return draft
