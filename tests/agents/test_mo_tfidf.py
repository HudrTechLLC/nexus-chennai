"""WS2-21: similar-MO via a fixed IDF table (D-027 TF-IDF fallback), behind NEXUS_MO_TFIDF (default off).

Acceptance (chief, 26 Oct): a pair's MO similarity is the same whichever candidate set fetched it, from either
direction, and in the Skeptic's recompute; the flag is off by default.
"""

from __future__ import annotations

import itertools
import json

import pytest
from agents_fixtures import ADYAR, FEATURES, HOUSEBREAK, VELACHERY, as_row

from app.agents import Candidate, Linker, Skeptic
from app.agents import linker as L
from app.agents.base import crime_from_row, features_from_row
from app.engines import mo_idf
from app.engines.similarity import build_mo_idf, mo_idf_cosine


def _f(cid):
    return features_from_row(as_row(FEATURES[cid]))


def _c(crime):
    return Candidate(crime_from_row(as_row(crime)), _f(crime["crime_id"]), query_ids={"q_case": "qc", "q_features": "qf"})


@pytest.fixture
def table(tmp_path, monkeypatch):
    t = build_mo_idf([_f(cid) for cid in FEATURES])
    p = tmp_path / "mo_idf.json"
    p.write_text(json.dumps(t), encoding="utf-8")
    monkeypatch.setattr(mo_idf, "table_path", lambda city=None, root=None: p)
    L._idf_cache.clear()
    return t


def _mo(pairs, other_id):
    sp = next(p for p in pairs if other_id in p.crimes)
    return next(f.value for f in sp.score.factors if f.factor == "mo_similarity")


def test_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv(L.MO_TFIDF_FLAG, raising=False)
    monkeypatch.delenv(L.MO_COSINE_FLAG, raising=False)
    assert L.mo_text_cosine() is None


def test_rare_keys_weigh_more_and_the_table_is_deterministic():
    recs = [{"mo": {"approach": "two wheeler"}, "visual_tags": ["helmet"]},
            {"mo": {"approach": "two wheeler"}, "visual_tags": ["red bike"]},
            {"mo": {"approach": "two wheeler"}, "visual_tags": []}]
    t = build_mo_idf(recs)
    assert t["idf"]["tag=red"] > t["idf"]["approach=two"]
    assert build_mo_idf(recs) == t and t["docs"] == 3


def test_cosine_is_exactly_symmetric(table):
    cos = mo_idf_cosine(table)
    for a, b in itertools.permutations(FEATURES, 2):
        assert cos(_f(a), _f(b)) == cos(_f(b), _f(a))


def test_pair_scores_the_same_from_any_candidate_set_and_direction(make_deps, table, monkeypatch):
    monkeypatch.setenv(L.MO_TFIDF_FLAG, "1")
    case, case_f = crime_from_row(as_row(ADYAR)), _f(ADYAR["crime_id"])
    lk = Linker(make_deps())
    wide = _mo(lk.score(case, case_f, [_c(VELACHERY), _c(HOUSEBREAK)], {}), VELACHERY["crime_id"])
    narrow = _mo(lk.score(case, case_f, [_c(VELACHERY)], {}), VELACHERY["crime_id"])
    back = _mo(lk.score(crime_from_row(as_row(VELACHERY)), _f(VELACHERY["crime_id"]), [_c(ADYAR)], {}),
               ADYAR["crime_id"])
    assert wide == narrow == back is not None


def test_skeptic_recompute_agrees_so_nothing_is_struck_for_mo(make_deps, table, monkeypatch):
    monkeypatch.setenv(L.MO_TFIDF_FLAG, "1")
    deps = make_deps()
    pairs = Linker(deps).score(crime_from_row(as_row(ADYAR)), _f(ADYAR["crime_id"]), [_c(VELACHERY)], {})
    res = Skeptic(deps).check(pairs[0])
    assert "mo_similarity" not in res.struck
    assert res.rechecked.get("mo_similarity") == _mo(pairs, VELACHERY["crime_id"])


def test_changes_the_mo_factor_only_when_on(make_deps, table, monkeypatch):
    case, case_f = crime_from_row(as_row(ADYAR)), _f(ADYAR["crime_id"])
    monkeypatch.delenv(L.MO_TFIDF_FLAG, raising=False)
    off = Linker(make_deps()).score(case, case_f, [_c(VELACHERY)], {})[0]
    monkeypatch.setenv(L.MO_TFIDF_FLAG, "1")
    on = Linker(make_deps()).score(case, case_f, [_c(VELACHERY)], {})[0]
    other = {f.factor: f.value for f in off.score.factors if f.factor != "mo_similarity"}
    assert other == {f.factor: f.value for f in on.score.factors if f.factor != "mo_similarity"}


def test_without_a_table_the_flag_falls_back_to_scorings_cosine(tmp_path, monkeypatch):
    monkeypatch.setattr(mo_idf, "table_path", lambda city=None, root=None: tmp_path / "missing.json")
    monkeypatch.setenv(L.MO_TFIDF_FLAG, "1")
    L._idf_cache.clear()
    assert L.mo_text_cosine() is None
