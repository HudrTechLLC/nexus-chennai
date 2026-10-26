"""Per-case appeal leaks (0007_08): Python side of the shared fixture tests/agents/appeal_leaks.json -> case_leaks.

The same fixture drives public.appeal_case_leak (supabase/tests/0007_08_appeal_case_leaks.py) and
apps/web/lib/appeals.ts (vitest), so the three cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.sanitiser import NAME_KIND, PLACE_KIND, area_label, case_leak, case_terms, leaks

CL = json.loads((Path(__file__).resolve().parent / "appeal_leaks.json").read_text("utf-8"))["case_leaks"]
TERMS = case_terms(CL["persons"], CL["address"])


@pytest.mark.parametrize("case", CL["leaky"], ids=lambda c: c["text"][:30])
def test_names_aliases_and_landmark_are_caught(case):
    assert case_leak(case["text"], TERMS) == case["kind"]


@pytest.mark.parametrize("text", CL["clean"])
def test_clean_texts_pass(text):
    assert case_leak(text, TERMS) is None


@pytest.mark.parametrize("extra", CL["more_addresses"], ids=lambda e: e["address"][:20])
def test_landmark_and_door_address_but_never_a_plain_road(extra):
    terms = case_terms([], extra["address"])
    assert all(case_leak(t, terms) == PLACE_KIND for t in extra["leaky"])
    assert all(case_leak(t, terms) is None for t in extra["clean"])


def test_leaks_uses_persons_when_the_caller_passes_them():
    case = {"location": {"address": CL["address"]}, "persons": CL["persons"]}
    assert NAME_KIND in leaks("Karthik was seen nearby", case)
    assert NAME_KIND not in leaks("Karthik was seen nearby", {"location": {"address": CL["address"]}})


def test_area_label_drops_a_leading_landmark():
    # Before 0007_08 the split needed a space before "near", so this label carried the landmark.
    label = area_label({"station_id": "PS-VADAPALANI-R5", "location": {"address": CL["address"]}})
    assert case_leak(label, TERMS) is None
    assert area_label({"station_id": "PS-ADYAR-J2", "location": {"address": "LB Road, Adyar"}}).startswith("Adyar (LB Road")
