"""Unit tests for the nine F2 factor functions (app.scoring.factors)."""

from __future__ import annotations

import math

import pytest

from app.scoring import factors as F

# A pair shaped like the spec D3.1 / D3.2 examples (Adyar <-> Velachery).
ADYAR = {
    "crime_id": "CHN-AD-2026-001182",
    "category": "robbery",
    "occurred_from": "2026-10-14T19:40:00+05:30",
    "location": {"lat": 13.0012, "lon": 80.2565},
    "weapon": None,
    "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "make_model": "Bajaj Pulsar 150",
                  "colour": "red", "plate": "TN 09 ?? 4471"}],
    "offenders_described": [{"count": 2, "helmet": "black with red stripe", "build": "thin", "age_band": "20-30"}],
}
VELACHERY = {
    "crime_id": "CHN-VL-2026-000877",
    "category": "robbery",
    "occurred_from": "2026-10-16T19:55:00+05:30",
    "location": {"lat": 12.9790, "lon": 80.2209},
    "weapon": None,
    "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "make_model": "Bajaj Pulsar 150",
                  "colour": "red", "plate": "TN09BX4471"}],
    "offenders_described": [{"count": 2, "helmet": "black helmet red stripe", "build": "thin", "age_band": "20-30"}],
}
MO_A = {
    "mo": {"approach": "two_wheeler_from_behind", "offender_count": 2, "target": "lone_pedestrian_woman",
           "target_item": "gold_chain", "escape": "two_wheeler_towards_main_road", "violence": "push",
           "time_band": "evening", "place_type": ["bus_stop", "main_road"], "disguise": ["helmet"], "verbal": None},
    "visual_tags": ["red motorcycle", "black helmet red stripe", "pillion rider"],
}
MO_B = {
    "mo": {"approach": "two_wheeler_from_behind", "offender_count": 2, "target": "lone_pedestrian_woman",
           "target_item": "gold_chain", "escape": "two_wheeler_towards_main_road", "violence": "push",
           "time_band": "evening", "place_type": ["bus_stop"], "disguise": ["helmet"], "verbal": None},
    "visual_tags": ["red motorcycle", "two riders"],
}
MO_HOUSEBREAK = {
    "mo": {"approach": "grille_cut", "offender_count": 1, "target": "locked_house", "target_item": "jewellery",
           "escape": "on_foot", "violence": None, "time_band": "night", "place_type": ["residential"],
           "disguise": [], "verbal": None},
    "visual_tags": ["grille cut", "torch"],
}


# ----- mo_similarity -------------------------------------------------------

def test_mo_similarity_high_for_same_pattern():
    assert F.mo_similarity(MO_A, MO_B) > 0.8


def test_mo_similarity_low_for_different_pattern():
    assert F.mo_similarity(MO_A, MO_HOUSEBREAK) < 0.2


def test_mo_similarity_identical_is_one():
    assert F.mo_similarity(MO_A, MO_A) == pytest.approx(1.0)


def test_mo_similarity_none_without_features():
    assert F.mo_similarity(None, MO_A) is None
    assert F.mo_similarity({}, MO_A) is None


def test_mo_similarity_is_symmetric():
    assert F.mo_similarity(MO_A, MO_B) == pytest.approx(F.mo_similarity(MO_B, MO_A))


# ----- space_time ----------------------------------------------------------

def test_space_time_matches_formula_with_band_boost():
    d = F.distance_km(ADYAR, VELACHERY)
    days = F.days_apart(ADYAR, VELACHERY)
    expected = min(1.0, math.exp(-d / 3) * math.exp(-days / 14) * F.SAME_BAND_BOOST)
    assert F.space_time(ADYAR, VELACHERY) == pytest.approx(expected)
    assert 3.0 < d < 5.0  # the spec example is "3.4 km apart"-ish


def test_space_time_no_boost_across_bands():
    morning = {**VELACHERY, "occurred_from": "2026-10-16T08:00:00+05:30"}
    d, days = F.distance_km(ADYAR, morning), F.days_apart(ADYAR, morning)
    assert F.space_time(ADYAR, morning) == pytest.approx(math.exp(-d / 3) * math.exp(-days / 14))


def test_space_time_same_place_same_time_is_one():
    assert F.space_time(ADYAR, ADYAR) == pytest.approx(1.0)


def test_space_time_none_without_location():
    assert F.space_time({**ADYAR, "location": {}}, VELACHERY) is None
    assert F.space_time({**ADYAR, "occurred_from": None}, VELACHERY) is None


# ----- vehicle -------------------------------------------------------------

def test_plate_full_match():
    assert F.plate_match("TN 09 BX 4471", "tn09bx4471") == 1.0


def test_plate_partial_match_in_range_and_grows_with_known_chars():
    two_unknown = F.plate_match("TN 09 ?? 4471", "TN09BX4471")
    four_unknown = F.plate_match("TN ?? ?? 4471", "TN09BX4471")
    assert 0.6 <= four_unknown < two_unknown <= 0.9


def test_plate_conflict_is_zero():
    assert F.plate_match("TN09BX4471", "TN09BX4472") == 0.0


def test_plate_right_aligned_when_lengths_differ():
    assert 0.6 <= F.plate_match("4471", "TN09BX4471") <= 0.9


def test_vehicle_uses_plates():
    assert 0.6 <= F.vehicle(ADYAR, VELACHERY) <= 0.9


def test_vehicle_description_only_is_capped():
    a = {**ADYAR, "vehicles": [{"type": "motorcycle", "colour": "red", "make_model": "Bajaj Pulsar 150"}]}
    b = {**VELACHERY, "vehicles": [{"type": "motorcycle", "colour": "red", "make_model": "Bajaj Pulsar 150"}]}
    assert F.vehicle(a, b) == pytest.approx(F.DESCRIPTION_ONLY_CAP)


def test_vehicle_ignores_victim_vehicles():
    a = {**ADYAR, "vehicles": [{"role": "victim", "plate": "TN09BX4471"}]}
    assert F.vehicle(a, VELACHERY) is None


def test_vehicle_anpr_sighting_near_both_scenes():
    a = {**ADYAR, "vehicles": []}
    b = {**VELACHERY, "vehicles": []}
    rows = [
        {"plate_text": "TN09BX4471", "crime_id": ADYAR["crime_id"]},
        {"plate_text": "TN 09 BX 4471", "crime_id": VELACHERY["crime_id"]},
    ]
    assert F.vehicle(a, b, rows) == F.ANPR_BOTH_SCENES
    assert F.vehicle(a, b, rows[:1]) is None


# ----- suspect_description -------------------------------------------------

def test_suspect_description_match():
    assert F.suspect_description(ADYAR["offenders_described"], VELACHERY["offenders_described"]) > 0.8


def test_suspect_description_ignores_protected_attributes():
    """LNK-13: religion, caste, community and similar keys never change the value."""
    base = F.suspect_description(ADYAR["offenders_described"], VELACHERY["offenders_described"])
    tainted_a = [{**ADYAR["offenders_described"][0], "religion": "x", "caste": "y", "community": "z"}]
    tainted_b = [{**VELACHERY["offenders_described"][0], "religion": "q", "caste": "r", "community": "s"}]
    assert F.suspect_description(tainted_a, tainted_b) == base
    only_protected = [{"religion": "x", "caste": "y"}]
    assert F.suspect_description(only_protected, only_protected) is None


def test_suspect_description_age_band_adjacent_half():
    a = [{"age_band": "20-30"}]
    assert F.suspect_description(a, [{"age_band": "30-40"}]) == 0.5
    assert F.suspect_description(a, [{"age_band": "50-60"}]) == 0.0


def test_suspect_description_none_without_descriptions():
    assert F.suspect_description([], VELACHERY["offenders_described"]) is None


# ----- weapon_tool ---------------------------------------------------------

def test_weapon_same_class():
    assert F.weapon_tool({"weapon": "knife"}, {"weapon": "small blade"}) == 1.0


def test_weapon_different_class():
    assert F.weapon_tool({"weapon": "knife"}, {"weapon": "rope"}) == 0.0


def test_weapon_unrecorded_is_none():
    assert F.weapon_tool(ADYAR, VELACHERY) is None
    assert F.weapon_tool({"weapon": "knife"}, {"weapon": None}) is None


def test_weapon_dict_class():
    assert F.weapon_tool({"weapon": {"class": "cutter"}}, {"weapon": "grille cutter"}) == 1.0


# ----- target_profile ------------------------------------------------------

def test_target_profile():
    assert F.target_profile(MO_A, MO_B) == 1.0
    assert F.target_profile(MO_A, MO_HOUSEBREAK) == 0.0
    assert F.target_profile(None, MO_A) is None


# ----- forensic ------------------------------------------------------------

def test_forensic():
    assert F.forensic(["FP-0091"], ["FP-0091", "DNA-12"]) == 1.0
    assert F.forensic(["FP-0091"], ["FP-0092"]) == 0.0
    assert F.forensic([], ["FP-0091"]) is None
    assert F.forensic(None, None) is None


# ----- corroboration -------------------------------------------------------

def test_corroboration_counts_only_items_mentioning_both():
    a, b = ADYAR["crime_id"], VELACHERY["crime_id"]
    items = [{"crime_ids": [a, b]}, {"crime_ids": [a]}, {"crime_ids": [b, a, "other"]}]
    assert F.corroboration(items, a, b) == pytest.approx(1 - math.exp(-2 / 2))


def test_corroboration_none_when_nothing_ties_them():
    a, b = ADYAR["crime_id"], VELACHERY["crime_id"]
    assert F.corroboration([], a, b) is None
    assert F.corroboration(None, a, b) is None
    assert F.corroboration([{"crime_ids": [a]}], a, b) is None


def test_corroboration_is_bounded():
    a, b = "A", "B"
    assert F.corroboration([{"crime_ids": [a, b]}] * 50, a, b) <= 1.0


# ----- offender_return -----------------------------------------------------

def test_offender_return_shared_person():
    pa = [{"person_ref": "P-44120", "mo_overlap": 0.9}]
    pb = [{"person_ref": "P-44120", "mo_overlap": 0.7}, {"person_ref": "P-1"}]
    assert F.offender_return(pa, pb) == pytest.approx(0.7)
    assert F.offender_return([{"person_ref": "P-1"}], [{"person_ref": "P-1"}]) == 1.0


def test_offender_return_none_without_shared_person():
    assert F.offender_return([{"person_ref": "P-1"}], [{"person_ref": "P-2"}]) is None
    assert F.offender_return(None, [{"person_ref": "P-1"}]) is None


# ----- all factors stay in [0, 1] ------------------------------------------

def test_all_factor_values_bounded():
    values = [
        F.mo_similarity(MO_A, MO_B),
        F.space_time(ADYAR, VELACHERY),
        F.vehicle(ADYAR, VELACHERY),
        F.suspect_description(ADYAR["offenders_described"], VELACHERY["offenders_described"]),
        F.target_profile(MO_A, MO_B),
    ]
    assert all(v is not None and 0.0 <= v <= 1.0 for v in values)
