"""Live Zetaris REST returns every value as text; declared numeric columns are coerced at the adapter.

Regression for run_2743a75c (take A's FIR CHN-AD-2026-001232, 27 Oct): q_offender_return.mo_overlap came back
as "0.5", and factors.offender_return raised "'>' not supported between instances of 'str' and 'float'" on the
first pair whose crimes shared a released offender. DuckDB (sample mode, the judge path) already returns floats,
so the sample path is untouched.
"""

from __future__ import annotations

import pytest

from app.adapters import zetaris as Z
from app.config import Settings
from app.scoring import factors as F
from app.tracing import Tracer

COLS = Z.NAMED_QUERIES["q_offender_return"].columns


def rest_row(person: str, mo_overlap, days="12") -> list:
    """One q_offender_return row exactly as REST returns it: every value a string."""
    vals = {"person_ref": person, "release_id": "R-1", "released_on": "2026-09-30", "release_type": "bail",
            "residence_ward": "173", "near_home": "true", "prior_mo_tags": "two_wheeler_from_behind",
            "matched_tags": "two_wheeler_from_behind", "mo_overlap": mo_overlap, "days_since_release": days,
            "sheet_id": "HS-1", "sheet_category": "chain_snatching", "sheet_active": "true"}
    return [vals[c] for c in COLS]


def test_q_offender_return_declares_its_numeric_columns():
    assert set(Z.NAMED_QUERIES["q_offender_return"].numeric) == {"mo_overlap", "days_since_release"}
    assert set(Z.NAMED_QUERIES["q_offender_return"].numeric) <= set(COLS)


@pytest.mark.parametrize("raw,want", [("0.5", 0.5), (" 0.667 ", 0.667), ("1", 1.0), (0.25, 0.25), (3, 3.0),
                                      (None, None), ("", None), ("n/a", None)])
def test_coerce_numeric_values(raw, want):
    row = Z.coerce_numeric([rest_row("P-1", raw)], COLS, ("mo_overlap",))[0]
    assert row[COLS.index("mo_overlap")] == want
    assert row[COLS.index("person_ref")] == "P-1" and row[COLS.index("residence_ward")] == "173"  # text stays text


def _live_client(tmp_path, rows):
    s = Settings(_env_file=None, sample_mode=False, zetaris_api_key="test-key", supabase_url="",
                 supabase_service_role_key="")
    c = Z.ZetarisClient(s, tracer=Tracer("num-test", tmp_path, echo=False))
    c._post = lambda *a, **k: [list(r) for r in rows]  # the REST answer, no network
    return c


def test_live_rest_rows_come_back_numeric(tmp_path):
    c = _live_client(tmp_path, [rest_row("P-1", "0.5"), rest_row("P-2", "abc", days="")])
    res = c.named("q_offender_return", agent="t", mo_tags="two_wheeler_from_behind", ward="173",
                  since="2026-10-26T19:40:00+05:30")
    assert res.source == "zetaris"
    d = res.dicts()
    assert d[0]["mo_overlap"] == 0.5 and d[0]["days_since_release"] == 12.0
    assert d[1]["mo_overlap"] is None and d[1]["days_since_release"] is None
    assert d[0]["person_ref"] == "P-1" and d[0]["near_home"] is True


@pytest.mark.parametrize("a,b,want", [("0.667", "0.5", 0.5),   # both text (the run_2743a75c shape)
                                      ("0.667", None, 0.667),  # text and missing
                                      (0.667, "0.5", 0.5)])    # float and text
def test_offender_return_on_live_rows_no_longer_raises(tmp_path, a, b, want):
    persons = []
    for ov in (a, b):
        c = _live_client(tmp_path, [rest_row("P-shared", ov)])
        persons.append(c.named("q_offender_return", agent="t", mo_tags="x", ward="1", since="2026-10-01").dicts())
    assert F.offender_return(persons[0], persons[1]) == pytest.approx(want)


def test_without_coercion_the_factor_raises_exactly_as_in_the_run():
    """Documents the failure the boundary prevents (raw REST strings straight into the factor)."""
    raw = [dict(zip(COLS, rest_row("P-shared", "0.5")))]
    with pytest.raises(TypeError, match="'>' not supported between instances of 'str' and 'float'"):
        F.offender_return(raw, raw)


def test_sample_rows_are_untouched():
    rows = [rest_row("P-1", 0.5)]
    assert Z.coerce_numeric(rows, COLS, ()) is rows


# =====================
# Flags: REST sends "true"/"false" text, and "false" is truthy in Python (nexus-2, chief)
# =====================

def test_flag_columns_are_declared():
    assert set(Z.NAMED_QUERIES["q_offender_return"].boolean) == {"near_home", "sheet_active"}
    assert Z.NAMED_QUERIES["q_case"].boolean == ("synthetic",)
    assert Z.NAMED_QUERIES["q_cases"].boolean == ("synthetic",)
    for q in Z.NAMED_QUERIES.values():
        assert set(q.boolean) <= set(q.columns) and set(q.numeric) <= set(q.columns), q.name


@pytest.mark.parametrize("raw,want", [("true", True), ("false", False), ("TRUE", True), (" f ", False), ("t", True),
                                      ("1", True), ("0", False), (True, True), (False, False), (0, False),
                                      (None, None), ("", None), ("maybe", None)])
def test_coerce_boolean_values(raw, want):
    row = Z.coerce_boolean([rest_row("P-1", "0.5")], COLS, ("near_home",))[0]
    row[COLS.index("near_home")] = raw
    assert Z.coerce_boolean([row], COLS, ("near_home",))[0][COLS.index("near_home")] is want


def test_live_rows_false_is_false_not_truthy(tmp_path):
    row = rest_row("P-1", "0.5")
    row[COLS.index("near_home")] = "false"
    c = _live_client(tmp_path, [row])
    d = c.named("q_offender_return", agent="t", mo_tags="x", ward="1", since="2026-10-01").dicts()[0]
    assert d["near_home"] is False and d["sheet_active"] is True and d["mo_overlap"] == 0.5


def test_the_synthetic_flag_consumers_see_false_for_a_live_false(tmp_path):
    """The real consumer: alert_writer.py and extractor.py do bool(case.get("synthetic", True)). On a raw REST
    row "false" would be truthy and mark a real FIR's alert synthetic."""
    from app.agents.base import crime_from_row

    cols = Z.NAMED_QUERIES["q_case"].columns
    raw = ["" if c not in ("crime_id", "synthetic", "lat", "lon") else "x" for c in cols]
    raw[cols.index("crime_id")], raw[cols.index("synthetic")] = "CHN-AD-2026-009999", "false"
    raw[cols.index("lat")], raw[cols.index("lon")] = "13.004", "80.255"
    assert bool("false") is True  # the bug this prevents
    case = crime_from_row(_live_client(tmp_path, [raw]).named("q_case", agent="t", crime_id="x").dicts()[0])
    assert case["synthetic"] is False and bool(case.get("synthetic", True)) is False
