"""Planted false-link set #2 (fresh twins for the Skeptic retest): the same harness checks as set #1, on its own bundle.

Set #2 is drawn from data/eval/planted2/sample, an eval-only sample bundle built from a NEW generator seed (1027)
with every series as core (`python -m data.generator.sample --core-series all`). data/sample, the judge path and
set #1 are untouched. Set #1's twin crimes are excluded (read as an exclusion list only) and set #2 stops at the
first 8 twins that pass the recipe, in file order. Both the case file and the bundle are pinned by hash.

Rebuild (code only, ~5 min; the slow test below re-runs it when NEXUS_SLOW=1):
    cd services/api && SAMPLE_MODE=true NEXUS_STORE=memory NEXUS_SAMPLE_DIR=data/eval/planted2/sample PYTHONPATH=. \\
      python -m app.eval.planted_skeptic prepare --exclude-cases ../../engg/docs/eval/planted_skeptic_cases.json \\
      --max-twins 8 --out ../../engg/docs/eval/planted_skeptic_cases_set2.json
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

import test_planted_skeptic as T
from app.config import REPO_ROOT
from app.eval import planted_skeptic as P

BUNDLE = "data/eval/planted2/sample"
CASES2 = REPO_ROOT / "engg" / "docs" / "eval" / "planted_skeptic_cases_set2.json"
SPEC2 = json.loads(CASES2.read_text(encoding="utf-8"))
CASES2_SHA = "b77276cb21809dd7b5e3a7c5a7bf7c8e42989c1e180a031d1eacecc00989a85f"
BUNDLE_SHA = "25673ac60c5e06e4876751d2c1ae1517fdd6445690d2107fffd52ff6a1ba939d"
ARMS2 = [(c, n) for c in SPEC2["cases"] for n in c["near_misses"]]


@pytest.fixture
def bundle2(monkeypatch):
    monkeypatch.setenv("NEXUS_SAMPLE_DIR", BUNDLE)


def bundle_sha() -> str:
    root = REPO_ROOT / BUNDLE
    h = hashlib.sha256()
    for rel in sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()):  # same order on any OS
        h.update(rel.encode() + b"\0" + hashlib.sha256((root / rel).read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def test_the_case_file_and_the_bundle_are_the_pinned_ones():
    assert P.sha256_of(CASES2) == CASES2_SHA
    assert bundle_sha() == BUNDLE_SHA
    assert SPEC2["sample_dir"] == BUNDLE and SPEC2["sample_seed"] == 1027
    assert json.loads((REPO_ROOT / BUNDLE / "MANIFEST.json").read_text(encoding="utf-8"))["seed"] == 1027


def test_the_default_sample_dir_is_unchanged(monkeypatch):
    monkeypatch.delenv("NEXUS_SAMPLE_DIR", raising=False)
    assert T.sample_settings().sample_dir == REPO_ROOT / "data" / "sample"
    assert P.overlay_bundle() is None


def test_the_shape():
    kinds = [n["plant"]["kind"] for _, n in ARMS2]
    assert len(SPEC2["cases"]) == 8 and len(ARMS2) == 24
    assert {k: kinds.count(k) for k in set(kinds)} == {"offender_count": 8, "offender_age": 8,
                                                        "vehicle_identity": 5, "helmet": 3}
    assert all(n["reaches_skeptic"] for _, n in ARMS2)
    crimes = [x for c in SPEC2["cases"] for x in (c["a"], c["b"])]
    assert len(crimes) == len(set(crimes)) == 16
    assert len({c["group"] for c in SPEC2["cases"]}) == 5


def test_no_crime_of_set_one_and_no_protected_or_judge_id_is_used():
    used = {x for c in SPEC2["cases"] for x in (c["a"], c["b"])}
    assert not used & P.case_file_ids(T.CASES)
    assert not used & P.excluded_ids()
    assert set(SPEC2["excluded"]) >= P.case_file_ids(T.CASES) | P.excluded_ids()


@pytest.mark.parametrize("case,near", ARMS2, ids=[n["near_miss_id"] for _, n in ARMS2])
def test_each_near_miss_changes_exactly_one_fact_in_b(case, near, bundle2):
    T.test_each_near_miss_changes_exactly_one_fact_in_b(case, near)


def test_the_overlay_reaches_the_linker_and_the_skeptic_re_read(bundle2, monkeypatch):
    case, near = next((c, n) for c, n in ARMS2 if n["plant"]["kind"] == "vehicle_identity"
                      and "colour" in n["plant"]["old"] and n["plant"]["old"]["plate_digits"])
    monkeypatch.setattr(T, "VEHICLE_WITH_PLATE", (case, near))
    T.test_the_overlay_reaches_the_linker_and_the_skeptic_re_read()


def test_run_refuses_the_wrong_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_guard", lambda s: None)
    monkeypatch.delenv("NEXUS_SAMPLE_DIR", raising=False)
    with pytest.raises(SystemExit, match="NEXUS_SAMPLE_DIR=data/eval/planted2/sample"):
        P.run(T.sample_settings(), CASES2, CASES2_SHA, tmp_path / "out.json")
    monkeypatch.setenv("NEXUS_SAMPLE_DIR", BUNDLE)  # and set #1 refuses the set-2 bundle
    with pytest.raises(SystemExit, match="data/sample"):
        P.run(T.sample_settings(), T.CASES, P.sha256_of(T.CASES), tmp_path / "out.json")


@pytest.mark.skipif(os.environ.get("NEXUS_SLOW") != "1", reason="~5 min; set NEXUS_SLOW=1")
def test_the_case_file_is_what_prepare_produces(bundle2):
    fresh = P.prepare(T.sample_settings(), REPO_ROOT / "engg" / "docs" / "eval" / "planted_skeptic_cases.json", 8)
    assert json.dumps(fresh, indent=1, ensure_ascii=False) + "\n" == CASES2.read_text(encoding="utf-8")
