"""data.seed_appeals: synthetic published appeals for /appeals (chief, 26 Oct). No network: a fake REST client."""

from __future__ import annotations

import re
import uuid

import pytest

from data import seed_appeals as S


def _case(cid="CHN-GU-2026-001118", st="PS-GUINDY-J3", sub="chain_snatching", cat="robbery",
          ts="2026-10-02T02:30:00+00:00", generated=True):
    return {"crime_id": cid, "source_row_id": str(uuid.uuid5(S.GEN_NS, cid)) if generated else "console",
            "station_id": st, "fir_no": "118/2026", "category": cat, "sub_type": sub, "occurred_from": ts,
            "h3_r8": "88618c4f49fffff", "address": "near Sri Lakshmi Kalyana Mandapam, 4th Street, Guindy"}


MO = {"offender_count": 1, "approach": "two_wheeler_from_behind", "disguise": ["black_helmet_with_red_stripe"],
      "escape": "on_two_wheeler_towards_main_road", "target_item": "gold_chain",
      "place_type": ["Sri Lakshmi Kalyana Mandapam"]}


def test_appeal_is_built_from_templates_only():
    a = S.build(_case(), "Guindy (J3)", MO)
    text = " ".join([a["title"], a["summary"], a["area_label"], *a["looking_for"]])
    assert a["title"] == "Chain snatching in Guindy" and a["area_label"] == "Guindy"
    assert "One morning in Guindy" in a["summary"] and "wore a helmet" in a["summary"]
    # Nothing from the case's free text: no address, landmark, FIR number, ids, raw MO values, numbers.
    for leak in ("Lakshmi", "Mandapam", "4th Street", "118/2026", "CHN-", "PS-", "red_stripe", "main_road"):
        assert leak not in text
    assert not re.search(r"\d", text)
    assert S.problems(a, _case()) == []
    assert a["approved_by"] == "station_officer:PS-GUINDY-J3" and a["sanitiser_model"] == "seed:template"
    assert a["synthetic"] is True and a["week"] == "2026-W40" and a["time_window"] == "Morning"


def test_unknown_mo_values_add_nothing():
    a = S.build(_case(), "Guindy (J3)", {"approach": "something_new", "escape": "teleported", "offender_count": 9})
    assert a["summary"].startswith("One morning in Guindy, a woman's gold chain was snatched. Police are asking")


def test_ids_are_stable_and_shaped_like_the_apps():
    a, b = S.build(_case(), "Guindy (J3)", MO), S.build(_case(), "Guindy (J3)", None)
    assert a["public_incident_id"] == b["public_incident_id"] == S.appeal_id("CHN-GU-2026-001118", 2026)
    assert re.fullmatch(r"PI-2026-[0-9A-F]{6}", a["public_incident_id"])


class FakeRest:
    def __init__(self, crimes, features=(), taken=()):
        self.tables = {"crimes": crimes, "crime_features": list(features),
                       "public_incidents": [{"crime_id": c} for c in taken],
                       "stations": [{"station_id": s, "name": s.split("-")[1].title() + " (X)"} for s in S.STATIONS]}

    def get(self, table, **params):
        return self.tables[table]


def test_selection_skips_excluded_series_console_and_taken_cases():
    red = "CHN-AD-2026-001071"  # a Red Pulsar member (data/sample/_truth/series.json)
    crimes = [_case("CHN-GU-2026-000001", sub="murder"),                     # sub-type never seeded
              _case("CHN-GU-2026-000002", generated=False),                  # console FIR
              _case(S.JUDGE[1]),                                             # judge case
              _case("CHN-GU-2026-000003"),                                   # already has an appeal
              _case(red),                                                    # Red Pulsar
              _case("CHN-GU-2026-000004", sub="mobile_snatching"),
              _case("CHN-GU-2026-000005", sub="chain_snatching")]
    picked = S.select(FakeRest(crimes, taken=["CHN-GU-2026-000003"]))
    assert [c["crime_id"] for c, _ in picked] == ["CHN-GU-2026-000005"]  # one per station, preferred sub-type


def test_selection_prefers_unused_sub_types_and_cases_with_mo():
    crimes = [_case("CHN-GU-2026-000010", st="PS-GUINDY-J3"),
              _case("CHN-MM-2026-000011", st="PS-MAMBALAM-R1"),
              _case("CHN-MM-2026-000012", st="PS-MAMBALAM-R1", sub="street_robbery")]
    picked = S.select(FakeRest(crimes, features=[{"crime_id": "CHN-GU-2026-000010", "mo": MO}]))
    assert [(c["crime_id"], c["sub_type"]) for c, _ in picked] == [
        ("CHN-GU-2026-000010", "chain_snatching"), ("CHN-MM-2026-000012", "street_robbery")]


@pytest.mark.parametrize("sub", S.SUB_TYPES)
def test_every_sub_type_has_text_that_names_only_its_own_crime(sub):
    a = S.build(_case(sub=sub), "Egmore (F2)", None)
    assert S.problems(a, _case(sub=sub)) == []
