"""The pre-registered rules + vehicle baseline (engg/docs/eval/STRONGER_BASELINE_PREREG.md)."""

from __future__ import annotations

from app.scoring.baseline import (baseline_link, rules_and_vehicle_link, rules_plus_vehicle_link,
                                  vehicle_match)

A = {"crime_id": "A", "category": "robbery", "occurred_from": "2026-10-01T20:00:00+05:30",
     "location": {"lat": 13.0, "lon": 80.25},
     "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "colour": "red", "plate": "TN09??4471"}]}
NEAR = {"occurred_from": "2026-10-10T20:00:00+05:30", "location": {"lat": 13.01, "lon": 80.25}}
FAR = {"occurred_from": "2026-11-20T20:00:00+05:30", "location": {"lat": 13.10, "lon": 80.25}}  # 50 days, ~11 km


def veh(**kw):
    return [{"role": "used_by_offender", "type": "motorcycle", "colour": "red", **kw}]


def test_plate_fragment_of_four_known_characters_matches():
    assert vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate="TN09B?4471")})
    assert vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate="?? 4471")})


def test_fewer_than_four_known_characters_or_a_conflict_does_not_match():
    assert not vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate="??71")})
    # a conflicting plate never matches, even with the same type and colour
    assert not vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate="TN09??4472")})


def test_without_a_plate_type_and_colour_decide():
    assert vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate=None)})
    assert not vehicle_match(A, {**A, "crime_id": "B", "vehicles": veh(plate=None, colour="blue")})
    assert not vehicle_match(A, {**A, "crime_id": "B", "vehicles": []})
    # only offender vehicles count
    victim = [{"role": "victim", "type": "motorcycle", "colour": "red", "plate": "TN09AB4471"}]
    assert not vehicle_match(A, {**A, "crime_id": "B", "vehicles": victim})


def test_primary_is_rules_or_vehicle_within_the_same_category():
    far_same_bike = {**A, **FAR, "crime_id": "B"}
    assert not baseline_link(A, far_same_bike)
    assert rules_plus_vehicle_link(A, far_same_bike)          # the vehicle carries it beyond the window
    near_other_bike = {**A, **NEAR, "crime_id": "C", "vehicles": veh(plate="KA01ZZ9999")}
    assert rules_plus_vehicle_link(A, near_other_bike)        # the rules window alone is enough
    assert not rules_plus_vehicle_link(A, {**far_same_bike, "category": "theft"})
    assert not rules_plus_vehicle_link(A, A)


def test_strict_needs_both_the_window_and_the_vehicle():
    assert rules_and_vehicle_link(A, {**A, **NEAR, "crime_id": "B"})
    assert not rules_and_vehicle_link(A, {**A, **FAR, "crime_id": "B"})
    assert not rules_and_vehicle_link(A, {**A, **NEAR, "crime_id": "C", "vehicles": veh(plate="KA01ZZ9999")})
