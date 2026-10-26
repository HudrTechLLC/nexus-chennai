"""H-MEM facade (spec P4/E4): analyst decisions become bounded score adjustments.

    from app.engines import hmem
    hmem.record_decision("LA-913", "reject", "different_offenders", "one used a car", pair)
    adj = hmem.adjust(pair)   # {"delta": -0.04, "memory_ids": ["mem-1"], "reason": "..."}

`pair` describes the two crimes of a candidate link: `{"a": {...features}, "b": {...features}}`
(`left`/`right` or `crimes: [a, b]` also work). Ids, timestamps, coordinates and free text
are ignored; the MO features (crime type, area, entry method, vehicle, weapon, time band,
...) are what memories match on.

Rules:
- a decision becomes a memory tagged with its polarity (approve +1, reject -1, other 0),
  and reinforces earlier memories of the same pattern (same polarity: helpful,
  opposite: not_helpful), all written to the trust ledger;
- adjust() sums polarity x relevance x STEP over the retrieved memories and clamps the
  result to +-MAX_DELTA (0.08). The clamp is applied in code, always.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.engines import _runtime
from app.engines.hmem.core import HMEM

__all__ = ["adjust", "record_decision", "configure", "instance", "pair_text", "MAX_DELTA", "STEP"]

ENGINE = "hmem"
MAX_DELTA = 0.08
STEP = 0.1
# An explicit analyst decision starts above the reference default (0.7): it is direct human input.
DECISION_CONFIDENCE = 0.8
POLARITY = {"approve": 1, "approved": 1, "confirm": 1, "reject": -1, "rejected": -1}

_IGNORED_KEY_PARTS = ("id", "_at", "date", "time_utc", "lat", "lon", "lng", "h3", "text", "narrative",
                      "summary", "note", "url", "synthetic", "score")

_instance: HMEM | None = None


def configure(persist_dir: str | Path | None = None, clock: Callable[[], int] | None = None) -> HMEM:
    """(Re)open the memory over `persist_dir` (default logs/hmem). A new call = a new session."""
    global _instance
    if persist_dir is None:
        from app.config import get_settings

        persist_dir = get_settings().logs_dir / "hmem"
    _instance = HMEM(persist_dir=persist_dir, clock=clock, actor="analyst")
    return _instance


def instance() -> HMEM:
    return _instance or configure()


def _sides(pair: dict[str, Any]) -> tuple[dict, dict]:
    if "a" in pair and "b" in pair:
        return pair["a"], pair["b"]
    if "left" in pair and "right" in pair:
        return pair["left"], pair["right"]
    crimes = pair.get("crimes")
    if isinstance(crimes, list) and len(crimes) == 2:
        return crimes[0], crimes[1]
    raise ValueError("pair needs a/b, left/right or crimes=[a, b]")


def _features(side: dict[str, Any], prefix: str = "") -> list[str]:
    out: list[str] = []
    for key in sorted(side):
        k = key.lower()
        if any(part == k or k.endswith(part) or k.startswith(part + "_") for part in _IGNORED_KEY_PARTS):
            continue
        value = side[key]
        if isinstance(value, dict):
            out += _features(value, f"{prefix}{key}.")
        elif isinstance(value, (list, tuple)):
            out += [str(v) for v in value if isinstance(v, (str, int)) and not isinstance(v, bool)]
        elif isinstance(value, str) and value.strip():
            out.append(value.strip())
    return out


def pair_text(pair: dict[str, Any]) -> str:
    """Deterministic MO description of a pair: shared features first, then each side's own."""
    a, b = (_features(s) for s in _sides(pair))
    shared = [f for f in dict.fromkeys(a) if f in b]
    only_a = [f for f in dict.fromkeys(a) if f not in b]
    only_b = [f for f in dict.fromkeys(b) if f not in a]
    parts = [f"Shared: {', '.join(shared) or 'none'}."]
    if only_a or only_b:
        parts.append(f"Differs: {', '.join(only_a) or 'none'} versus {', '.join(only_b) or 'none'}.")
    return " ".join(parts)


def _clamp(x: float) -> float:
    return max(-MAX_DELTA, min(MAX_DELTA, x))


def adjust(pair: dict) -> dict:
    """Bounded score adjustment from memories similar to this pair."""
    if _runtime.backend() == "sidecar":
        from app.engines import _sidecar

        out = _sidecar.call("hmem/adjust", {"pair": pair, "query": pair_text(pair)})
        out["delta"] = round(_clamp(float(out["delta"])), 3)
    else:
        mem = instance()
        query = pair_text(pair)
        hits = mem.query(query, where=lambda m: any(t.startswith("decision:") for t in m["tags"]))
        raw, used, reasons = 0.0, [], []
        for m, relevance in hits:
            polarity = int(next((t.split(":", 1)[1] for t in m["tags"] if t.startswith("polarity:")), "0"))
            if polarity == 0:
                continue
            raw += polarity * relevance * STEP
            used.append(m["id"])
            reason = next((t.split(":", 1)[1] for t in m["tags"] if t.startswith("reason:")), "")
            reasons.append(f"{m['id']} {'approved' if polarity > 0 else 'rejected'}"
                           f"{' (' + reason + ')' if reason else ''} relevance {relevance:.2f}")
        delta = round(_clamp(raw), 3)
        out = {"delta": delta, "memory_ids": used,
               "reason": "; ".join(reasons) if reasons else "no similar analyst decisions in memory",
               "raw_delta": round(raw, 4)}
    _runtime.emit(ENGINE, "adjust", pair_text(pair)[:200],
                  f"delta {out['delta']:+.3f} from {len(out['memory_ids'])} memories")
    return out


def record_decision(alert_id: str, decision: str, reason_code: str | None, note: str | None, pair: dict) -> None:
    """Store an analyst decision as a memory, reinforce similar ones, write the ledger."""
    decision = decision.lower().strip()
    polarity = POLARITY.get(decision, 0)
    text = pair_text(pair)
    # The memory content is the pattern itself, so later pairs match on MO, not on the
    # decision wording. Decision, reason and note travel in tags and provenance.
    content = text
    tags = [f"decision:{decision}", f"polarity:{polarity}", f"alert:{alert_id}"]
    if reason_code:
        tags.append(f"reason:{reason_code}")
    if _runtime.backend() == "sidecar":
        from app.engines import _sidecar

        res = _sidecar.call("hmem/record", {"content": content, "tags": tags, "query": text, "polarity": polarity,
                                                "confidence": DECISION_CONFIDENCE})
        mem_id, reinforced = res["memory_id"], res["reinforced"]
    else:
        mem = instance()
        reinforced = []
        if polarity:
            for m, _ in mem.query(text, where=lambda m: any(t.startswith("polarity:") for t in m["tags"])):
                prior = int(next(t.split(":", 1)[1] for t in m["tags"] if t.startswith("polarity:")))
                if prior:
                    mem.feedback(m["id"], "helpful" if prior == polarity else "not_helpful")
                    reinforced.append(m["id"])
        rec = mem.add(content, source=f"analyst-decision:{alert_id}", tags=tags, confidence=DECISION_CONFIDENCE,
                      provenance={"origin": "analyst_decision", "alert_id": alert_id, "decision": decision,
                                  "reason_code": reason_code, "note": note})
        mem_id = rec["id"]
    _runtime.emit(ENGINE, "record_decision", f"{alert_id} {decision} {reason_code or ''}".strip(),
                  f"memory {mem_id}; reinforced {len(reinforced)}")
