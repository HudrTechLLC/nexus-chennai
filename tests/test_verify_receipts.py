"""scripts/verify_receipts.py: Nightshift receipt signatures, bucket separation, and no secrets or prompt text out."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verify_receipts", ROOT / "scripts" / "verify_receipts.py")
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)

FIXTURES = vr.load_fixtures(vr.FIXTURES)


def test_every_committed_fixture_receipt_verifies():
    assert FIXTURES, "the sample fixtures should carry signed receipts"
    assert {vr.check_envelope(e) for e in FIXTURES} == {"valid"}


def test_a_changed_body_or_signature_fails():
    env = copy.deepcopy(FIXTURES[0])
    env["body"]["receipt"]["usage"]["output_tokens"] += 1
    assert vr.check_envelope(env) == "bad_signature"
    env = copy.deepcopy(FIXTURES[0])
    sig = bytearray(vr.base64.b64decode(env["sig_b64"]))
    sig[0] ^= 1
    env["sig_b64"] = vr.base64.b64encode(bytes(sig)).decode()
    assert vr.check_envelope(env) == "bad_signature"
    assert vr.check_envelope({"body": {}, "pubkey_b64": "nope", "sig_b64": "x"}) == "malformed"
    assert vr.check_envelope({"pubkey_b64": FIXTURES[0]["pubkey_b64"]}) == "malformed"


def _log(envs):
    by_id = {}
    for e in envs:
        by_id.setdefault(vr.request_id(e), []).append(e)
    return by_id


def test_live_degraded_and_replayed_are_counted_apart():
    a, b, c = FIXTURES[:3]
    bad = copy.deepcopy(c)
    bad["body"]["ts_ms"] += 1
    log = _log([a, b, bad])
    trace = [
        {"receipt_id": vr.request_id(a), "status": "ok"},
        {"receipt_id": vr.request_id(a), "status": "ok"},  # repeated row: one distinct id
        {"receipt_id": vr.request_id(bad), "status": "ok"},
        {"receipt_id": "chatcmpl-missing", "status": "ok"},
        {"receipt_id": vr.request_id(b), "status": "degraded"},
        {"receipt_id": vr.request_id(b), "status": "replayed"},
        {"receipt_id": None, "status": "error", "action": "model_call"},
        {"receipt_id": vr.request_id(a), "status": "degraded", "action": "extract_features"},
    ]
    r = vr.build_report(trace, log, {"facts": {}, "keys": {}}, FIXTURES)
    assert (r["live"]["ids"], r["live"]["verified"]) == (3, 1)
    assert r["live"]["not_in_log"] == ["chatcmpl-missing"]
    assert r["live"]["bad_signature"] == [vr.request_id(bad)]
    assert (r["degraded"]["ids"], r["degraded"]["verified"]) == (1, 1)
    assert (r["replayed_trace"]["ids"], r["replayed_trace"]["verified"]) == (1, 1)
    assert r["replayed_fixtures"]["signature_valid"] == len(FIXTURES)
    # a fixture id seen in a live trace row is reported as an overlap, not hidden
    assert vr.request_id(a) in r["overlap_fixture_and_live_ids"]
    # a model call with no receipt id stays in the denominator; another event citing a receipt is its own bucket
    assert r["model_calls_without_receipt"] == {"error": 1}
    assert r["trace_model_calls"] == {"rows": 7, "rows_with_receipt": 6, "distinct_receipt_ids": 4,
                                      "rows_repeating_an_id": 2}
    citing = r["other_events_citing_receipts"]
    assert (citing["verified"], citing["also_a_live_model_call"]) == (1, 1)
    assert r["overlap_live_and_degraded_ids"] == []


def test_claim_names_the_number_of_keys():
    assert "every receipt uses the same key" in vr.claim_text(1)
    assert "2 different keys" in vr.claim_text(2) and "same key" not in vr.claim_text(2)


def test_report_holds_no_receipt_body_or_prompt_text():
    log = _log(FIXTURES)
    trace = [{"receipt_id": vr.request_id(e), "status": "ok"} for e in FIXTURES]
    text = json.dumps(vr.build_report(trace, log, {"facts": {}, "keys": {}}, FIXTURES), ensure_ascii=False)
    assert "prompt_preview" not in text and '"body"' not in text
    previews = [e["body"]["receipt"].get("prompt_preview") for e in FIXTURES]
    assert all(p and p[:40] not in text for p in previews)


def test_committed_report_holds_no_prompt_text():
    path = ROOT / "logs" / "receipts_verification.json"
    if not path.exists():
        pytest.skip("no committed report")
    text = path.read_text(encoding="utf-8")
    assert "prompt_preview" not in text and '"body"' not in text
    assert all(e["body"]["receipt"].get("prompt_preview", "")[:40] not in text for e in FIXTURES)


def test_errors_never_print_the_key(tmp_path, monkeypatch, capsys):
    key = "FAKE-KEY-for-a-test-QX7w2ZpL9"
    (tmp_path / "k").write_text(key, encoding="utf-8")
    (tmp_path / "log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY_FILE", str(tmp_path / "k"))
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")  # nothing listens: the read fails
    rc = vr.main(["--log", str(tmp_path / "log.jsonl"), "--out", str(tmp_path / "out.json")])
    out = capsys.readouterr()
    assert rc == 1
    assert key[:8] not in out.out + out.err
    assert not (tmp_path / "out.json").exists()
