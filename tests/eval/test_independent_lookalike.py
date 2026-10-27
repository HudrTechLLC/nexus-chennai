"""The independent look-alike test (INDEPENDENT_LOOKALIKE_PREREG) is deterministic: re-running the rule on the
pinned cases reproduces the committed results exactly, and every case is marked synthetic."""

from __future__ import annotations

import json

from app.eval import independent_lookalike as IL


def test_rerun_matches_committed_results():
    committed = json.loads(IL.OUT.read_text(encoding="utf-8"))
    assert IL.run() == committed
    assert committed["primary_drop_rate"]["dropped"] == 10 and committed["guard_twin_false_drop"]["dropped"] == 2


def test_every_case_is_synthetic():
    doc = json.loads(IL.CASES.read_text(encoding="utf-8"))
    assert doc["synthetic"] is True
    assert all(p[s]["synthetic"] is True for p in doc["pairs"] for s in ("a", "b"))
