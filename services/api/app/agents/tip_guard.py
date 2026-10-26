"""Tip Guard (spec E3, rule R8). Every public tip passes this before any agent reads it.

The verdict comes from the Scout Intent engine (`scout_intent.classify(text, "tip")`,
owned by nexus-2). This agent applies the verdict: quarantined tips go no further, urgent
tips are flagged for the 112 banner, and only clean or urgent tips reach the Extractor.
If the engine fails, the tip is quarantined (fail closed).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import AgentDeps, short

AGENT = "Tip Guard"
PASS_ACTIONS = ("clean", "urgent")


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
            status = "ok" if action == "clean" else action
        except Exception as exc:  # fail closed
            guard = {"verdict": "quarantine", "intent": None, "risk": ["guard_error"], "injection": False,
                     "threat": False, "engine": "scout_intent", "error": short(str(exc))}
            status = "error"
        self.deps.tracer.emit(AGENT, "screen_tip", input_summary=str(tip_id),
                              output_summary=short({k: guard[k] for k in ("verdict", "intent", "risk")}),
                              engine="scout_intent", status=status)
        return {**tip, "guard": guard}

    @staticmethod
    def passes(screened_tip: Mapping[str, Any]) -> bool:
        return (screened_tip.get("guard") or {}).get("verdict") in PASS_ACTIONS
