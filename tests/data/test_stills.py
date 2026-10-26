"""Synthetic CCTV stills (WS1-09): deterministic, keyed like record_evidence, accepted by the storage policy."""

import hashlib
import json
import re

import pytest

from data.generator.cli import generate
from data.generator.stills import build

POLICY = re.compile(r"^[A-Z]+-[A-Z0-9]+-\d{4}-\d+/[0-9a-f-]{36}\.(jpg|png|webp|pdf|mp4|mp3|m4a|ogg|webm|wav)$")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    p = tmp_path_factory.mktemp("gen")
    generate(42, p, scale=0.02)
    build(p)
    return p


def _rows(p):
    return [json.loads(x) for x in (p / "supabase" / "evidence_media.jsonl").read_text(encoding="utf-8").splitlines()]


def test_rows_match_record_evidence_and_the_storage_policy(gen):
    rows = _rows(gen)
    assert 23 <= len(rows) <= 69
    for r in rows:
        assert POLICY.match(r["storage_path"]) and r["storage_path"].startswith(r["crime_id"] + "/")
        assert r["evidence_id"] == "EV-" + r["storage_path"].split("/")[1].split(".")[0]
        assert r["kind"] == "cctv_still" and r["synthetic"] is True and r["custody"][0]["action"] == "seeded"
        body = (gen / "evidence" / r["storage_path"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == r["sha256"] == r["custody"][0]["sha256"] and body[:2] == b"\xff\xd8"


def test_hero_still_uses_the_spec_camera(gen):
    hero = [r for r in _rows(gen) if r["crime_id"] == "CHN-AD-2026-001182"]
    assert hero and all(r["camera_id"] == "CAM-LB-0192" for r in hero)


def test_rebuild_gives_the_same_bytes(gen):
    before = {r["evidence_id"]: r["sha256"] for r in _rows(gen)}
    build(gen)
    assert {r["evidence_id"]: r["sha256"] for r in _rows(gen)} == before
