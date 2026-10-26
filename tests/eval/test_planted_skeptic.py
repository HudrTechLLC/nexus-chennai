"""Planted false-link test for the Skeptic (engg/docs/eval/PLANTED_SKEPTIC_PREREG.md): the harness itself.

These run on the bundled sample data with no model call. They pin what the pre-registration promises: one planted
fact per near-miss, rewritten consistently in B and nowhere else; the Linker's inputs and the Skeptic's own re-read
both see it; no protected or judge crime is used; the case file is what `prepare` produces; step 2 refuses to run
anywhere it could write shared state.
"""

from __future__ import annotations

import json
import re

import pytest

from app.agents.base import crime_from_row, features_from_row
from app.config import REPO_ROOT, Settings
from app.eval import planted_skeptic as P

CASES = REPO_ROOT / "engg" / "docs" / "eval" / "planted_skeptic_cases.json"
PREREG = REPO_ROOT / "engg" / "docs" / "eval" / "PLANTED_SKEPTIC_PREREG.md"
SPEC = json.loads(CASES.read_text(encoding="utf-8"))

# The only paths each plant may change in B (narrative/statements/tags are text forms of the same fact).
ALLOWED = {
    "vehicle_colour": {".vehicles[0].colour", ".narrative", ".statements", ".visual_tags", ".features.visual_tags"},
    "vehicle_make": {".vehicles[0].make_model", ".narrative", ".statements", ".visual_tags", ".features.visual_tags"},
    "offender_count": {".offenders_described[0].count", ".mo.offender_count", ".features.mo.offender_count",
                       ".narrative", ".statements", ".visual_tags", ".features.visual_tags"},
    "offender_age": {".offenders_described[0].age_band", ".narrative", ".statements"},
    "helmet": {".offenders_described[0].helmet", ".mo.disguise", ".features.mo.disguise", ".narrative",
               ".statements", ".visual_tags", ".features.visual_tags"},
}


def sample_settings() -> Settings:
    return Settings(_env_file=None, sample_mode=True, supabase_url="", supabase_service_role_key="",
                    zetaris_api_key="", meterless_runtime_token="")


def diff_paths(x, y, p=""):
    if type(x) is not type(y):
        yield p
        return
    if isinstance(x, dict):
        for k in set(x) | set(y):
            yield from diff_paths(x.get(k), y.get(k), f"{p}.{k}")
    elif isinstance(x, list):
        if len(x) != len(y):
            yield p
            return
        for i, (u, v) in enumerate(zip(x, y)):
            yield from diff_paths(u, v, f"{p}[{i}]")
    elif x != y:
        yield p


def norm(path: str) -> str:
    """'.statements[2].text' -> '.statements'; '.features.visual_tags[1]' -> '.features.visual_tags'."""
    for root in (".statements", ".visual_tags", ".features.visual_tags", ".mo.disguise", ".features.mo.disguise"):
        if path.startswith(root):
            return root
    return path


def load(deps, cid):
    c = crime_from_row(deps.query("q_case", agent="t", crime_id=cid)[0][0])
    f = deps.query("q_features", agent="t", ids=cid)[0]
    return c, (features_from_row(f[0]) if f else None)


ARMS = [(c, n) for c in SPEC["cases"] for n in c["near_misses"]]


@pytest.mark.parametrize("case,near", ARMS, ids=[n["near_miss_id"] for _, n in ARMS])
def test_each_near_miss_changes_exactly_one_fact_in_b(case, near):
    deps = P._deps(sample_settings(), "t", None)
    b, fb = load(deps, case["b"])
    plant = P.Plant.from_dict(near["plant"])
    c2, f2 = P.apply_plant(plant, b, fb)
    changed = {norm(p) for p in diff_paths(b, c2)} | {norm(p) for p in diff_paths(fb, f2)}
    assert changed, "the plant changed nothing"
    assert changed <= ALLOWED[plant.kind], changed - ALLOWED[plant.kind]
    # the structured field carries the new value; the old value is gone from B's visible fact
    if plant.kind == "vehicle_colour":
        assert c2["vehicles"][0]["colour"] == plant.new
        assert not re.search(rf"\b{plant.old}[ _](motorcycle|bike)", json.dumps(c2["statements"]), re.I)
    if plant.kind == "vehicle_make":
        assert c2["vehicles"][0]["make_model"] == plant.new
        assert plant.old.lower() not in json.dumps(c2).lower()
    if plant.kind == "offender_count":
        assert c2["offenders_described"][0]["count"] == plant.new == f2["mo"]["offender_count"]
    if plant.kind == "offender_age":
        assert c2["offenders_described"][0]["age_band"] == plant.new
        assert c2["victims"] == b["victims"]  # a victim sharing the band is never touched
    if plant.kind == "helmet":
        assert c2["offenders_described"][0]["helmet"] == plant.new


def test_the_overlay_reaches_the_linker_and_the_skeptic_re_read():
    case, near = ARMS[0]
    plant = P.Plant.from_dict(near["plant"])
    deps = P._deps(sample_settings(), "t", plant)
    sp, (_, _, b, _) = P.score_pair(deps, case["a"], case["b"])
    assert b["vehicles"][0]["colour"] == plant.new and sp.crime_b["vehicles"][0]["colour"] == plant.new
    # what the Skeptic's _fresh re-query reads (q_case by id) is planted too; A is untouched
    again, _ = load(deps, case["b"])
    a, _ = load(deps, case["a"])
    assert again["vehicles"][0]["colour"] == plant.new and a["vehicles"][0]["colour"] == plant.old


def test_no_protected_or_judge_crime_is_used():
    used = {x for c in SPEC["cases"] for x in (c["a"], c["b"])}
    assert not used & P.excluded_ids()
    assert {"CHN-AD-2026-001182", "CHN-VL-2026-000877", "CHN-AD-2026-001231"} <= P.excluded_ids()
    assert "CHN-KU-2025-000078" in P.excluded_ids()  # a judge input


def test_the_case_file_is_what_prepare_produces_and_matches_the_prereg_hash():
    fresh = json.dumps(P.prepare(sample_settings()), indent=1, ensure_ascii=False) + "\n"
    assert fresh == CASES.read_text(encoding="utf-8")
    assert P.sha256_of(CASES) in PREREG.read_text(encoding="utf-8")


def test_balanced_plants_and_every_near_miss_reaches_the_skeptic():
    kinds = [n["plant"]["kind"] for _, n in ARMS]
    assert len(ARMS) == 20 and len(SPEC["cases"]) == 10
    assert {k: kinds.count(k) for k in set(kinds)} == {k: 4 for k in ALLOWED}
    assert all(n["reaches_skeptic"] for _, n in ARMS)


@pytest.mark.parametrize("env", ["SUPABASE_URL", "NEXUS_RECORD_FIXTURES", "ENGINES_PERSIST", "ZETARIS_API_KEY"])
def test_step_two_refuses_anything_that_could_write_shared_state(env, monkeypatch):
    monkeypatch.setenv(env, "x")
    with pytest.raises(SystemExit, match="refusing"):
        P._guard(Settings(_env_file=None, sample_mode=True, meterless_runtime_token="t"))


def test_step_two_refuses_live_data_a_store_or_no_token(monkeypatch):
    for k in ("SUPABASE_URL", "NEXUS_RECORD_FIXTURES", "ENGINES_PERSIST", "ZETARIS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit, match="SAMPLE_MODE"):
        P._guard(Settings(_env_file=None, sample_mode=False, meterless_runtime_token="t"))
    with pytest.raises(SystemExit, match="token"):
        P._guard(Settings(_env_file=None, sample_mode=True, meterless_runtime_token=""))
    monkeypatch.setenv("NEXUS_STORE", "supabase")
    with pytest.raises(SystemExit, match="NEXUS_STORE"):
        P._guard(Settings(_env_file=None, sample_mode=True, meterless_runtime_token="t"))


def test_run_refuses_a_case_file_that_is_not_the_pre_registered_one(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_guard", lambda s: None)
    with pytest.raises(SystemExit, match="pre-registered"):
        P.run(sample_settings(), CASES, "0" * 64, tmp_path / "out.json")


def test_summary_counts_the_paired_primary_metric():
    r = [{"case_id": "PS-01", "id": "PS-01", "arm": "twin", "verdict": "approve", "model_critique": "applied"},
         {"case_id": "PS-01", "id": "PS-01a", "arm": "planted", "plant_kind": "helmet", "verdict": "drop",
          "model_critique": "applied"},
         {"case_id": "PS-01", "id": "PS-01b", "arm": "planted", "plant_kind": "vehicle_make", "verdict": "send_back",
          "model_critique": "applied"},
         {"case_id": "PS-02", "id": "PS-02", "arm": "twin", "verdict": "drop", "model_critique": "applied"},
         {"case_id": "PS-02", "id": "PS-02a", "arm": "planted", "plant_kind": "helmet", "verdict": "drop",
          "model_critique": "applied"},
         {"case_id": "PS-02", "id": "PS-02b", "arm": "planted", "plant_kind": "offender_age", "verdict": "drop",
          "model_critique": "unavailable"}]
    s = P.summarise(r)
    assert s["near_misses_scored"] == 3 and s["unavailable"] == ["PS-02b"]
    assert s["primary_dropped_while_twin_approved"] == 1  # PS-02a dropped, but its twin was dropped too
    assert s["planted_dropped"] == 2 and s["planted_dropped_or_sent_back"] == 3
    assert s["twins_approved"] == 1 and s["twins_dropped"] == 1
    assert s["by_plant_kind"]["helmet"] == {"n": 2, "dropped_twin_approved": 1, "dropped": 2, "sent_back": 0}


def test_the_prompts_are_the_pre_registered_ones():
    # Changing either prompt after pre-registration needs a new pre-registration, not a silent re-run.
    import hashlib

    from app.agents.linker import RATIONALE_PROMPT
    from app.agents.skeptic import SKEPTIC_PROMPT

    text = PREREG.read_text(encoding="utf-8")
    assert hashlib.sha256(SKEPTIC_PROMPT.encode()).hexdigest() in text
    assert hashlib.sha256(RATIONALE_PROMPT.encode()).hexdigest() in text
