"""Independent look-alike test of the Skeptic contradiction rule (engg/docs/eval/INDEPENDENT_LOOKALIKE_PREREG.md).

Offline and deterministic: for each hand-written pair, call `contradiction.contradictions(a, b)` and apply the
same decision as `Skeptic.contradiction_step` for a pair the Skeptic would approve with nothing reconciling it
(`rechecked = {}`, nothing struck). No model, database, Zetaris or Nightshift access. One pass.

Run: `cd services/api && SAMPLE_MODE=true python -m app.eval.independent_lookalike`
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..agents import contradiction as K

ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "engg/docs/eval/independent_lookalike_cases.json"
OUT = ROOT / "engg/docs/eval/independent_lookalike_results.json"
PINNED_CASES = "93f72b97baaee720f93e2a0c3dca7ebe2d1c4e0b2d2c7e9ff9d18937b1ea9ece"
PINNED_RULE = "9e088b135744b383861c7726317dbb283c2082fe645bfd0a89423764912930ac"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def decide(a: dict, b: dict) -> tuple[bool, list[dict]]:
    """Dropped iff a hard contradiction exists and no confirmed reconciling factor (none here)."""
    found = K.contradictions(a, b)
    dropped = bool(found) and not K.reconciled_by({}, [])
    return dropped, found


def rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def run() -> dict:
    rule_path = Path(K.__file__)
    shas = {"cases": sha(CASES), "contradiction_py": sha(rule_path)}
    if shas["cases"] != PINNED_CASES or shas["contradiction_py"] != PINNED_RULE:
        raise SystemExit(f"pinned input changed: {shas}")
    pairs = json.loads(CASES.read_text(encoding="utf-8"))["pairs"]
    rows = []
    for p in pairs:
        dropped, found = decide(p["a"], p["b"])
        rows.append({"pair_id": p["pair_id"], "stratum": p["stratum"], "label": p["label"], "differs": p["differs"],
                     "dropped": dropped, "contradictions": found})
    fl = [r for r in rows if r["label"] == "false_link"]
    tw = [r for r in rows if r["label"] == "true_twin"]
    per = {s: {"dropped": sum(r["dropped"] for r in fl if r["stratum"] == s),
               "n": sum(r["stratum"] == s for r in fl)} for s in ("S1", "S2", "S3")}
    clean = [r for r in tw if r["stratum"] == "twin_clean"]
    werr = [r for r in tw if r["stratum"] == "twin_witness_error"]
    dropped_fl = sum(r["dropped"] for r in fl)
    dropped_tw = sum(r["dropped"] for r in tw)
    return {
        "synthetic": True,
        "pinned": shas,
        "primary_drop_rate": {"dropped": dropped_fl, "n": len(fl), "rate": rate(dropped_fl, len(fl)),
                              "pass_threshold": 0.60, "pass": rate(dropped_fl, len(fl)) >= 0.60},
        "guard_twin_false_drop": {"dropped": dropped_tw, "n": len(tw), "pass_max": 1, "pass": dropped_tw <= 1},
        "per_stratum": {s: {**v, "rate": rate(v["dropped"], v["n"])} for s, v in per.items()},
        "twins_clean_dropped": {"dropped": sum(r["dropped"] for r in clean), "n": len(clean)},
        "twins_witness_error_dropped": {"dropped": sum(r["dropped"] for r in werr), "n": len(werr)},
        "pairs": rows,
    }


def main() -> None:
    res = run()
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in res.items() if k != "pairs"}, indent=1))
    for r in res["pairs"]:
        print(r["pair_id"], "DROP" if r["dropped"] else "keep", "|", r["differs"], "|",
              K.describe(r["contradictions"]) if r["contradictions"] else "-")


if __name__ == "__main__":
    main()
