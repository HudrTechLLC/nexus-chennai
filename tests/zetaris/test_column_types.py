"""Live REST rows come back typed like their DuckDB sample twins (#25, after #430).

Zetaris REST serialises every value as text, so without declared column types the live path would hand
callers "25" for q_news.hours_after, "false" (truthy in Python) for q_news.category_hint, and "0.12" for
q_calls_near.km_from_scene, while sample mode (DuckDB, the judge path) returns an int, a bool and a float. No
consumer compares these today, so nothing crashes yet; this pins the live types to the sample types before one
does (the #430 crash came from exactly this gap). q_tip_corroboration.tags is JSON-array text in BOTH modes
(`get_json_object(..., '$.tags')` live, the same text in the sample), so it is deliberately not coerced.
"""

from __future__ import annotations

import pytest

from app.adapters import zetaris as Z
from app.config import Settings
from app.tracing import Tracer

HERO = "CHN-AD-2026-001182"  # has a news mention, a nearby 112 call and a corroborating tip in data/sample

DECLARED = {
    "q_news": ({"hours_after"}, {"category_hint"}),
    "q_calls_near": ({"lat", "lon", "km_from_scene", "minutes_from_start"}, set()),
    "q_tip_corroboration": (set(), set()),
}


def rest_text(v):
    """A value as Zetaris REST sends it: text, with SQL booleans as 'true'/'false' and NULL as null."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _client(tmp_path, *, sample: bool, rows=None):
    s = Settings(
        _env_file=None,
        sample_mode=sample,
        zetaris_api_key="" if sample else "test-key",
        supabase_url="",
        supabase_service_role_key="",
    )
    c = Z.ZetarisClient(s, tracer=Tracer("types-test", tmp_path, echo=False))
    if not sample:
        c._post = lambda *a, **k: [list(r) for r in rows]  # the REST answer, no network
    return c


@pytest.mark.parametrize("name", sorted(DECLARED))
def test_declared_types_are_real_output_columns(name):
    q = Z.NAMED_QUERIES[name]
    numeric, boolean = DECLARED[name]
    assert set(q.numeric) == numeric and set(q.boolean) == boolean
    assert set(q.numeric) <= set(q.columns) and set(q.boolean) <= set(q.columns)


@pytest.mark.parametrize("name", sorted(DECLARED))
def test_live_rest_row_matches_sample_twin_types(tmp_path, name):
    sample = _client(tmp_path / "s", sample=True).named(name, agent="t", crime_id=HERO)
    assert sample.source != "zetaris" and sample.rows, f"{name}: the sample twin should return a row for {HERO}"
    twin = sample.rows[0]
    live = _client(tmp_path / "l", sample=False, rows=[[rest_text(v) for v in twin]]).named(
        name, agent="t", crime_id=HERO
    )
    assert live.source == "zetaris"
    got, want = live.dicts()[0], sample.dicts()[0]
    for col in Z.NAMED_QUERIES[name].columns:
        g, w = got[col], want[col]
        if isinstance(w, bool) or w is None:
            assert g is w, f"{name}.{col}: live {g!r} vs sample {w!r}"
        elif isinstance(w, (int, float)):
            assert isinstance(g, (int, float)) and not isinstance(g, bool) and g == pytest.approx(w), (name, col, g, w)
        else:
            assert type(g) is type(w) and g == w, f"{name}.{col}: live {g!r} vs sample {w!r}"


def test_category_hint_false_text_is_false_not_truthy(tmp_path):
    cols = Z.NAMED_QUERIES["q_news"].columns
    row = {c: "x" for c in cols} | {"hours_after": "25", "category_hint": "false"}
    d = (
        _client(tmp_path, sample=False, rows=[[row[c] for c in cols]])
        .named("q_news", agent="t", crime_id=HERO)
        .dicts()[0]
    )
    assert d["category_hint"] is False and d["hours_after"] == 25.0


def test_tags_stay_json_text_in_both_modes(tmp_path):
    want = _client(tmp_path, sample=True).named("q_tip_corroboration", agent="t", crime_id=HERO).dicts()[0]["tags"]
    assert isinstance(want, str) and want.startswith("[")
