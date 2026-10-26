"""Scout Intent eval harness (spec E4; Meterless Scout docs/eval-harness.md metrics).

    python -m app.engines.scout_intent.eval        # prints the report, writes logs/feature_scout_intent.txt

Fixture sets (tests/engines/fixtures/scout_intent/, all synthetic):
- queries.jsonl (60) and tips.jsonl (87): the E4 set of 120 (t-001..t-060) plus live-miss shapes and
  hard negatives (t-061..t-087) added after the live screen; the rules were tuned on all of it.
- holdout.jsonl (40): written after tuning and never tuned on; reported separately.

Metrics: route accuracy (gate >= 0.9 on the 120), intent accuracy, injection recall
(gate: every injection quarantined), injection precision, emergency recall, and false
quarantines of legitimate tips.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.engines.scout_intent.core import QUERY_ROUTES, TIP_ROUTES, classify

FIXTURES = Path(__file__).resolve().parents[5] / "tests" / "engines" / "fixtures" / "scout_intent"
ROUTE_GATE = 0.9
BLOCKING = ("prompt_injection", "threat", "abuse", "spam")


def expected_route(row: dict) -> str:
    intent = row["expected_intent"]
    if row["kind"] == "query":
        return "quarantine" if intent == "prompt_injection" else QUERY_ROUTES[intent]
    return TIP_ROUTES[intent]


def load(name: str) -> list[dict]:
    with (FIXTURES / f"{name}.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evaluate(rows: list[dict]) -> dict:
    results = []
    for r in rows:
        out = classify(r["text"], r["kind"])
        results.append({**r, "got_route": out["route"], "got_intent": out["intent"], "action": out["action"],
                        "want_route": expected_route(r)})
    n = len(results)
    inj = [x for x in results if x["expected_intent"] == "prompt_injection"]
    flagged = [x for x in results if x["got_intent"] == "prompt_injection"]
    emerg = [x for x in results if x["expected_intent"] == "emergency"]
    legit = [x for x in results if x["kind"] == "tip" and x["expected_intent"] not in BLOCKING]
    return {
        "n": n,
        "route_accuracy": sum(x["got_route"] == x["want_route"] for x in results) / n if n else 0.0,
        "intent_accuracy": sum(x["got_intent"] == x["expected_intent"] for x in results) / n if n else 0.0,
        "injections": len(inj),
        "injections_quarantined": sum(x["action"] == "quarantine" for x in inj),
        "injection_precision": (sum(x["expected_intent"] == "prompt_injection" for x in flagged) / len(flagged)
                                if flagged else 1.0),
        "emergencies": len(emerg),
        "emergencies_urgent": sum(x["action"] == "urgent" for x in emerg),
        "false_quarantines": [x["id"] for x in legit if x["action"] == "quarantine"],
        "misses": [(x["id"], x["want_route"], x["got_route"]) for x in results if x["got_route"] != x["want_route"]],
    }


def report() -> tuple[str, dict]:
    queries, tips = load("queries"), load("tips")
    main = evaluate(queries + tips)
    hold = evaluate(load("holdout"))
    lines = [
        "# Scout Intent eval (Nexus implementation of the Meterless Scout spec)",
        f"run (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]
    for title, m in ((f"E4 set+: {len(queries)} queries + {len(tips)} tips (rules tuned on this set)", main),
                     ("Held-out set: 40 (written after tuning, never tuned on)", hold)):
        lines += [
            f"## {title}",
            f"fixtures:               {m['n']}",
            f"route accuracy:         {m['route_accuracy']:.3f}  (gate >= {ROUTE_GATE})",
            f"intent accuracy:        {m['intent_accuracy']:.3f}",
            f"injections quarantined: {m['injections_quarantined']}/{m['injections']}  (gate: all)",
            f"injection precision:    {m['injection_precision']:.3f}",
            f"emergencies -> urgent:  {m['emergencies_urgent']}/{m['emergencies']}",
            f"false quarantines:      {len(m['false_quarantines'])} {m['false_quarantines']}",
            f"misses (id, want, got): {m['misses']}",
            "",
        ]
    return "\n".join(lines), {"main": main, "holdout": hold}


def main() -> None:
    from app.config import get_settings

    text, _ = report()
    out = get_settings().logs_dir / "feature_scout_intent.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"written: {out}")


if __name__ == "__main__":
    main()
