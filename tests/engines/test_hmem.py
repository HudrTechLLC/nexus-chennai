"""Spec E4 H-MEM: the three-session test. Each session reopens memory from disk (a new instance)."""

import json

import pytest

from app.engines import hmem


from .conftest import CLOCK


REJECTED = {"a": {"crime_type": "chain snatching", "area": "Adyar", "time_band": "evening", "vehicle": "motorcycle"},
            "b": {"crime_type": "chain snatching", "area": "Adyar", "time_band": "evening", "vehicle": "car"}}
SIMILAR_TO_REJECTED = {
    "a": {"crime_type": "chain snatching", "area": "Adyar", "time_band": "evening", "vehicle": "motorcycle"},
    "b": {"crime_type": "chain snatching", "area": "Adyar", "time_band": "night", "vehicle": "car"}}
RED_PULSAR = {"a": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"},
              "b": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"}}
NEXT_RED_PULSAR = {"a": {"crime_type": "two-wheeler theft", "area": "Velachery", "vehicle": "red Pulsar"},
                   "b": {"crime_type": "two-wheeler theft", "area": "Guindy", "vehicle": "red Pulsar"}}


def _ledger(path):
    return [json.loads(line) for line in (path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]


def test_three_sessions_change_the_score(tmp_path):
    mem_dir = tmp_path / "mem"

    # Baseline: before any decision, nothing is applied.
    hmem.configure(mem_dir, clock=CLOCK)
    assert hmem.adjust(SIMILAR_TO_REJECTED)["delta"] == 0.0
    assert hmem.adjust(NEXT_RED_PULSAR)["delta"] == 0.0

    # Session 1: analyst rejects a pair, "same area, different offenders: one used a car".
    hmem.configure(mem_dir, clock=CLOCK)
    hmem.record_decision("LA-101", "reject", "different_offenders",
                         "same area, different offenders: one used a car", REJECTED)
    assert [e["action"] for e in _ledger(mem_dir)] == ["create"]

    # Session 2 (new instance, same directory): a similar pair's score drops and shows the memory.
    hmem.configure(mem_dir, clock=CLOCK)
    s2 = hmem.adjust(SIMILAR_TO_REJECTED)
    assert s2["delta"] < 0 and s2["memory_ids"] == ["mem-1"]
    assert "different_offenders" in s2["reason"]
    assert abs(s2["delta"]) <= hmem.MAX_DELTA
    last = _ledger(mem_dir)[-1]
    assert (last["memoryId"], last["action"]) == ("mem-1", "read")

    # Session 3: an approval of a red-Pulsar pair raises the next red-Pulsar pair.
    hmem.configure(mem_dir, clock=CLOCK)
    hmem.record_decision("LA-102", "approve", "same_offender", "same red Pulsar rider", RED_PULSAR)
    hmem.configure(mem_dir, clock=CLOCK)
    s3 = hmem.adjust(NEXT_RED_PULSAR)
    assert s3["delta"] > 0 and "mem-2" in s3["memory_ids"]
    assert abs(s3["delta"]) <= hmem.MAX_DELTA

    # Ledger lines exist for each step, append-only across sessions.
    actions = [(e["memoryId"], e["action"]) for e in _ledger(mem_dir)]
    assert ("mem-1", "create") in actions and ("mem-1", "read") in actions
    assert ("mem-2", "create") in actions and ("mem-2", "read") in actions
    assert actions.index(("mem-1", "create")) < actions.index(("mem-2", "create"))


def test_repeated_approvals_reinforce_the_pattern(tmp_path):
    hmem.configure(tmp_path / "m", clock=CLOCK)
    hmem.record_decision("LA-1", "approve", "same_offender", "", RED_PULSAR)
    one = hmem.adjust(NEXT_RED_PULSAR)["delta"]
    hmem.record_decision("LA-2", "approve", "same_offender", "", RED_PULSAR)
    two = hmem.adjust(NEXT_RED_PULSAR)["delta"]
    assert 0 < one < two <= hmem.MAX_DELTA
    feedback = [e for e in hmem.instance().ledger_entries() if e["action"] == "feedback"]
    assert feedback and feedback[0]["details"] == {"kind": "helpful", "delta": 0.05}


def test_unrelated_pair_is_not_adjusted(tmp_path):
    hmem.configure(tmp_path / "m", clock=CLOCK)
    hmem.record_decision("LA-1", "reject", "different_offenders", "one used a car", REJECTED)
    unrelated = {"a": {"crime_type": "cheating", "area": "Anna Nagar", "method": "online UPI fraud"},
                 "b": {"crime_type": "cheating", "area": "Tambaram", "method": "fake job offer"}}
    out = hmem.adjust(unrelated)
    assert out["delta"] == 0.0 and out["memory_ids"] == []


def test_memory_without_source_is_rejected(tmp_path):
    with pytest.raises((ValueError, RuntimeError)):
        hmem.configure(tmp_path / "m").add("x", source="", tags=[], confidence=0.8, provenance={})
