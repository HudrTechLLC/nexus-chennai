"""Every default-plan step must bind through the Zetaris parameter renderer (live and sample both use it).

Regression for #27: default_plan passed q_offender_return's mo_tags as a list, the renderer only binds scalars,
and the step failed "Unsupported parameter type: list" on every case with MO tags (6 of 20 in the live
spot-check, 13 in the sample eval), so offender_return got no data from the plan.
"""

from __future__ import annotations

from app.adapters.zetaris import NAMED_QUERIES, render
from app.agents.planner import default_plan

CASE = {"crime_id": "CHN-AD-2026-001182", "category": "robbery", "sub_type": "chain_snatching",
        "occurred_from": "2026-10-14T19:40:00+05:30", "location": {"ward": 176, "h3_r9": "89618c4f483ffff"},
        "vehicles": [{"role": "used_by_offender", "plate": "TN09??4471"}]}
FEATURES = {"entities": {"plates": ["TN09??4471"]}, "mo": {"approach": "two_wheeler_from_behind", "target": "woman_pedestrian",
                   "target_item": "gold_chain", "escape": "two_wheeler"}}


def test_default_plan_includes_offender_return_with_joined_tags():
    steps = {s.name: s.params for s in default_plan(CASE, FEATURES)}
    assert "q_offender_return" in steps
    assert steps["q_offender_return"]["mo_tags"] == \
        "two_wheeler_from_behind,woman_pedestrian,gold_chain,two_wheeler"  # as linker.py joins them


def test_every_default_plan_step_binds_in_both_modes():
    for step in default_plan(CASE, FEATURES):
        q = NAMED_QUERIES[step.name]
        params = {**(q.defaults or {}), **step.params}
        for sql in (q.lightning, q.sample):
            render(sql, params)  # raised TypeError("Unsupported parameter type: list") before #27
