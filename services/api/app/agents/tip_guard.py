"""Tip Guard (spec E3, rule R8). Every public tip passes this before any agent reads it.

The verdict comes from the Scout Intent engine (`scout_intent.classify(text, "tip")`,
owned by nexus-2). This agent applies the verdict: quarantined tips go no further, urgent
tips are flagged for the 112 banner, and only clean or urgent tips reach the Extractor.
If the engine fails, the tip is quarantined (fail closed).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .base import AgentDeps, short

AGENT = "Tip Guard"
PASS_ACTIONS = ("clean", "urgent")

# Summary + tags for tips.guard (read by Zetaris through tips_v, which never exposes the raw text).
# Built ONLY from this vocabulary, never copied from the tip: names, addresses and injected
# instructions cannot reach the summary, whatever the tip says (R8). Order = order in the summary.
TAG_VOCAB: dict[str, tuple[tuple[str, str], ...]] = {
    "count": (("two guys", "two people"), ("two men", "two people"), ("two boys", "two people"),
              ("three men", "three people"), ("group", "a group")),
    "colour": tuple((c, c) for c in ("red", "black", "white", "blue", "silver", "grey", "green", "yellow")),
    "vehicle": (("pulsar", "motorcycle"), ("bike", "motorcycle"), ("motorcycle", "motorcycle"),
                ("scooter", "scooter"), ("activa", "scooter"), ("auto", "autorickshaw"), ("cab", "car"),
                ("car", "car"), ("dzire", "car"), ("swift", "car"), ("van", "van"), ("lorry", "lorry")),
    "weapon": (("knife", "knife"), ("gun", "firearm"), ("pistol", "firearm"), ("rod", "iron rod"),
               ("sickle", "sickle"), ("aruval", "sickle")),
    "item": (("chain", "gold chain"), ("phone", "phone"), ("mobile", "phone"), ("bag", "bag"),
             ("cash", "cash"), ("jewel", "jewellery")),
    "wear": (("helmet", "helmet"), ("mask", "mask"), ("hood", "hood")),
    "place": (("bus stop", "bus stop"), ("tea shop", "tea shop"), ("temple", "temple"), ("market", "market"),
              ("railway", "railway station"), ("metro", "metro station"), ("atm", "ATM"), ("school", "school"),
              ("beach", "beach"), ("signal", "traffic signal"), ("petrol", "petrol bunk")),
    "time": (("night", "night"), ("evening", "evening"), ("morning", "morning"), ("afternoon", "afternoon"),
             ("every day", "repeated sightings"), ("every evening", "repeated sightings"), ("daily", "repeated sightings")),
}
_PLATE = re.compile(r"\bTN[\s-]?\d{2}[\s-]?[A-Z]{1,2}[\s-]?\d{3,4}\b", re.IGNORECASE)
MAX_TAGS = 10


def tip_tags(redacted_text: str | None) -> list[str]:
    """Vocabulary tags found in the PII-redacted tip text, plus normalised TN plates (`plate:TN22AB1234`)."""
    if not redacted_text:
        return []
    low = " " + re.sub(r"\[[^\]]*\]", " ", redacted_text.lower()) + " "  # drop "[phone redacted]" placeholders
    tags: list[str] = []
    for words in TAG_VOCAB.values():
        for word, tag in words:
            if re.search(rf"\b{re.escape(word)}\b", low) and tag not in tags:
                tags.append(tag)
    for m in _PLATE.finditer(redacted_text):
        plate = "plate:" + re.sub(r"[\s-]", "", m.group(0)).upper()
        if plate not in tags:
            tags.append(plate)
    return tags[:MAX_TAGS]


def tip_summary(guard: Mapping[str, Any], tags: list[str]) -> str | None:
    """Short, template-only summary; None for quarantined tips (nothing about them goes further)."""
    verdict = guard.get("verdict")
    if verdict not in PASS_ACTIONS:
        return None
    facts = [t for t in tags if not t.startswith("plate:")]
    plates = [t.split(":", 1)[1] for t in tags if t.startswith("plate:")]
    head = "Urgent tip (112 flagged)" if verdict == "urgent" else "Tip"
    if not facts and not plates:
        return f"{head}: no specific details recognised."
    body = ", ".join(facts)
    if plates:
        body += ("; " if body else "") + "plate " + ", ".join(plates)
    return f"{head} mentions: {body}."[:200]


class TipGuard:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    def screen(self, tip: Mapping[str, Any]) -> dict[str, Any]:
        """Return the tip with a `guard` block; `guard.verdict` is clean, urgent or quarantine."""
        tip_id = tip.get("tip_id")
        try:
            res = self.deps.engines.scout_intent.classify(str(tip.get("text") or ""), "tip")
            action = res.get("action")
            if action not in ("clean", "quarantine", "urgent"):
                raise ValueError(f"unknown action {action!r}")
            risk = list(res.get("risk") or [])
            guard = {
                "verdict": action,
                "intent": res.get("intent"),
                "risk": risk,
                "injection": "prompt_injection" in risk or res.get("intent") == "prompt_injection",
                "threat": "threat" in risk or res.get("intent") == "threat",
                "engine": "scout_intent",
                "emergency": bool(res.get("emergency")),
                # PII-redacted text from the engine; the Extractor reads this, never the raw tip.
                "redacted_text": res.get("redacted_text"),
            }
            guard["tags"] = tip_tags(guard["redacted_text"]) if action in PASS_ACTIONS else []
            guard["summary"] = tip_summary(guard, guard["tags"])
            status = "ok" if action == "clean" else action
        except Exception as exc:  # fail closed
            guard = {"verdict": "quarantine", "intent": None, "risk": ["guard_error"], "injection": False,
                     "threat": False, "engine": "scout_intent", "error": short(str(exc)), "tags": [],
                     "summary": None}
            status = "error"
        self.deps.tracer.emit(AGENT, "screen_tip", input_summary=str(tip_id),
                              output_summary=short({k: guard[k] for k in ("verdict", "intent", "risk")}),
                              engine="scout_intent", status=status)
        return {**tip, "guard": guard}

    @staticmethod
    def passes(screened_tip: Mapping[str, Any]) -> bool:
        return (screened_tip.get("guard") or {}).get("verdict") in PASS_ACTIONS
