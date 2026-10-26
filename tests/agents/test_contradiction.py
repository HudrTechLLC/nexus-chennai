"""Hard-contradiction step of the Skeptic (SKEPTIC_CONTRADICTION_PREREG).

The rule: a stated difference on a distinctive descriptor drops an approved pair in code, unless a confirmed
forensic or offender_return factor reconciles it. Less detail, unknown values and overlapping age bands are
never contradictions.
"""

from __future__ import annotations

import csv
import json

import pytest

from app.agents import contradiction as K
from app.agents.base import crime_from_row
from app.agents.skeptic import Skeptic, SkepticResult
from app.config import REPO_ROOT, Settings
from app.eval import planted_skeptic as P

SET1 = json.loads((REPO_ROOT / "engg/docs/eval/planted_skeptic_cases.json").read_text(encoding="utf-8"))


def sample_settings() -> Settings:
    return Settings(_env_file=None, sample_mode=True, supabase_url="", supabase_service_role_key="",
                    zetaris_api_key="", meterless_runtime_token="")


def crime(count=2, age="20-30", helmet="black with red stripe", colour="red", make="Bajaj Pulsar 150",
          plate="TN09B?4471", more=()):
    return {"offenders_described": [{"count": count, "age_band": age, "helmet": helmet, "build": "thin"}, *more],
            "vehicles": [{"role": "used_by_offender", "type": "motorcycle", "colour": colour, "make_model": make,
                          "plate": plate}]}


# =====================
# The rule, field by field
# =====================

@pytest.mark.parametrize("b", [
    crime(),
    crime(make="Bajaj Pulsar"),                       # less detail (live C802: "Pulsar 150" vs "Pulsar")
    crime(helmet="black helmet with red stripe"),     # filler words
    crime(helmet="black"),                            # less detail
    crime(colour="Red"),
    crime(plate="TN09??4471"),                        # unread positions
    crime(plate="??4471"),
    crime(age="25-35"),                               # overlapping bands
    crime(age="30-40"),                               # touching bands overlap
    crime(count=None, age=None, helmet=None, colour=None, make=None, plate=None),
    crime(helmet="unknown", colour="not seen"),
])
def test_compatible_descriptions_are_not_contradictions(b):
    assert K.contradictions(crime(), b) == []


@pytest.mark.parametrize("b,kind,field", [
    (crime(count=1), "offender_count", "count"),
    (crime(age="50-60"), "offender_age", "age_band"),
    (crime(helmet="plain yellow"), "helmet", "helmet"),
    (crime(helmet="no helmet"), "helmet", "helmet"),
    (crime(colour="blue"), "vehicle_identity", "colour"),
    (crime(make="Yamaha FZ"), "vehicle_identity", "make_model"),
    (crime(plate="TN09B?9788"), "vehicle_identity", "plate"),
])
def test_each_stated_difference_is_a_contradiction(b, kind, field):
    found = K.contradictions(crime(), b)
    assert [(c["kind"], c["field"]) for c in found] == [(kind, field)]


def test_no_helmet_is_its_own_value():
    assert K.text_compatible("no helmet", "without helmet")
    assert not K.text_compatible("no helmet", "white full-face")
    assert not K.text_compatible("white full-face", "no helmet")


def test_grey_and_gray_are_one_colour():
    assert K.colour_compatible("grey", "Gray") and not K.colour_compatible("grey", "red")


def test_several_described_offenders_contradict_only_if_no_pair_is_compatible():
    two = crime(more=[{"count": 1, "age_band": "50-60", "helmet": "plain yellow"}])
    assert K.contradictions(two, crime(count=1, age="50-60", helmet="plain yellow")) == []
    assert K.contradictions(two, crime()) == []


def test_a_plate_needs_two_read_positions_to_conflict():
    assert K.plate_compatible("TN09B?4471", "?????????1")      # one shared read position
    assert K.plate_compatible("TN09B?4471", "?????????2")      # one differing read is not enough
    assert not K.plate_compatible("4471", "9788")


def test_reconciled_only_by_confirmed_forensic_or_offender_return():
    assert K.reconciled_by({"forensic": 1.0}, []) == ["forensic"]
    assert K.reconciled_by({"offender_return": 0.8}, []) == ["offender_return"]
    assert K.reconciled_by({"forensic": 1.0}, ["forensic"]) == []          # struck by the Skeptic
    assert K.reconciled_by({"forensic": 0.2, "vehicle": 1.0}, []) == []    # weak, or not a reconciling factor
    assert K.reconciled_by({}, []) == []


# =====================
# Wired into Skeptic.review (not check)
# =====================

def _vehicle_plant_arm():
    for c in SET1["cases"]:
        for n in c["near_misses"]:
            if n["plant"]["kind"] == "vehicle_identity" and n["plant"]["old"].get("plate_digits"):
                return c, n
    raise AssertionError("set #1 has a plated vehicle plant")


def test_review_drops_a_planted_contradiction_in_code_without_a_model_call():
    case, near = _vehicle_plant_arm()
    deps = P._deps(sample_settings(), "t", P.Plant.from_dict(near["plant"]))
    sp, _ = P.score_pair(deps, case["a"], case["b"])
    assert sp.score.alert
    r = Skeptic(deps).review([sp], critique=True)[0]
    assert r.verdict == "drop" and r.drop_source == "contradiction"
    assert {c["kind"] for c in r.contradictions} == {"vehicle_identity"}
    assert r.model_critique is None and r.critique.startswith("Hard contradiction (code)")
    assert not [e for e in deps.tracer.read() if e["action"] == "model_call"]
    block = r.review_block()
    assert block["verdict"] == "rejected" and block["drop_source"] == "contradiction"


def test_check_alone_is_unchanged_so_the_linking_eval_is_not_affected():
    case, near = _vehicle_plant_arm()
    deps = P._deps(sample_settings(), "t", P.Plant.from_dict(near["plant"]))
    sp, _ = P.score_pair(deps, case["a"], case["b"])
    r = Skeptic(deps).check(sp)
    assert r.verdict == "approve" and r.drop_source is None and r.contradictions == []


def test_a_confirmed_reconciling_factor_keeps_the_pair():
    case, near = _vehicle_plant_arm()
    deps = P._deps(sample_settings(), "t", P.Plant.from_dict(near["plant"]))
    sp, _ = P.score_pair(deps, case["a"], case["b"])
    sk = Skeptic(deps)
    r = sk.check(sp)
    r.rechecked = {**r.rechecked, "forensic": 1.0}
    sk.contradiction_step(r)
    assert r.verdict == "approve" and r.drop_source is None and r.contradictions
    assert any(e["action"] == "contradiction_reconciled" for e in deps.tracer.read())


def test_only_approved_pairs_are_touched():
    r = SkepticResult(pair=None, verdict="send_back", rows=(crime(), crime(count=1)))  # type: ignore[arg-type]
    Skeptic(None).contradiction_step(r)  # type: ignore[arg-type]
    assert r.verdict == "send_back" and r.contradictions == []


def test_the_twins_and_the_hero_pair_pass_untouched():
    deps = P._deps(sample_settings(), "t", None)
    for a, b in [("CHN-AD-2026-001182", "CHN-VL-2026-000877"), *[(c["a"], c["b"]) for c in SET1["cases"]]]:
        sp, _ = P.score_pair(deps, a, b)
        r = Skeptic(deps).review([sp], critique=False)[0]
        assert r.drop_source is None and r.contradictions == [], (a, b)


def test_no_true_series_pair_in_the_sample_contradicts():
    """Pre-check recorded in the prereg: 0 of 97 truth series pairs; every decoy does (by the generator's design)."""
    deps = P._deps(sample_settings(), "t", None)

    def load(cid):
        return crime_from_row(deps.query("q_case", agent="t", crime_id=cid)[0][0])

    rows = list(csv.DictReader((REPO_ROOT / "data/sample/_truth/pairs.csv").open(encoding="utf-8")))
    series = [r for r in rows if r["label"] == "series"]
    decoys = [r for r in rows if r["label"] == "decoy"]
    assert len(series) == 97 and not [r for r in series if K.contradictions(load(r["crime_a"]), load(r["crime_b"]))]
    assert all(K.contradictions(load(r["crime_a"]), load(r["crime_b"])) for r in decoys)


# =====================
# The harness counts a code drop as a decision, not as "unavailable"
# =====================

def test_a_code_drop_is_decided_and_counts_as_a_drop():
    def arm(cid, aid, kind, verdict, mc, src=None):
        return {"case_id": cid, "id": aid, "arm": "twin" if kind is None else "planted", "plant_kind": kind,
                "verdict": verdict, "model_critique": mc, "drop_source": src, "features_source": "stored"}
    r = [arm("T1", "T1", None, "approve", "applied"),
         arm("T1", "T1a", "helmet", "drop", "not_sent", "contradiction"),
         arm("T1", "T1b", "offender_age", "send_back", "applied"),
         arm("T2", "T2", None, "drop", "not_sent", "contradiction"),
         arm("T2", "T2a", "helmet", "drop", "unavailable")]
    s = P.summarise(r)
    assert s["unavailable"] == ["T2a"]
    assert s["planted_decided"] == 2 and s["planted_drop_rate"] == 0.5 and s["planted_dropped_by_code"] == 1
    assert s["twin_false_drops"] == 1 and s["twin_false_drop_rate"] == 0.5
    assert s["primary_dropped_while_twin_approved"] == 1 and s["near_misses_scored"] == 2
