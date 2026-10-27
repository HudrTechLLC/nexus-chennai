"""#15: every Nightshift reply's signed receipt is checked at call time (Ed25519), in degraded mode only.

Valid -> receipt_verified=True. Missing, tampered or malformed -> receipt_verified=False, a "receipt unverified
(degraded)" trace note, a per-run count the alert writer copies onto the alert, and the reply is still returned
(never refused). Sample-mode replays are checked too and never fail the judge path.
"""

import base64
import hashlib
import json

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import receipts
from app.adapters.nightshift import NightshiftClient
from app.config import Settings
from app.tracing import Tracer


def settings(**kw):
    base = dict(meterless_base_url="http://ns.test/v1", meterless_runtime_token="tok-test",
                lane_fast="nvidia/nemotron-3.5-lightning-30b-a3b", sample_mode=False)
    base.update(kw)
    return Settings(_env_file=None, **base)


KEY = Ed25519PrivateKey.generate()  # throwaway test key, never a real one
KEY_SHA256 = hashlib.sha256(KEY.public_key().public_bytes_raw()).hexdigest()


def envelope(body=None, *, tamper=False, key=None):
    """A receipt envelope signed with a throwaway test key (never a real one)."""
    key = key or KEY
    body = body or {"receipt": {"request_id": "req_test1", "receipt_id": "rcpt_req_test1"}, "app": "nexus-chennai"}
    sig = key.sign(receipts.canonical(body))
    pub = key.public_key().public_bytes_raw()
    if tamper:
        body = {**body, "app": "someone-else"}  # altered after signing
    return {"body": body, "pubkey_b64": base64.b64encode(pub).decode(), "sig_b64": base64.b64encode(sig).decode()}


def handler_with(meterless):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        data = {"id": "chatcmpl-1", "model": body["model"], "choices": [{"message": {"content": "OK"}}]}
        if meterless is not None:
            data["meterless"] = meterless
        return httpx.Response(200, json=data, headers={"meterless-receipt-id": "rcpt_req_test1"})

    return handler


def call(tmp_path, meterless, pin=KEY_SHA256):
    tracer = Tracer("rv", tmp_path, echo=False)
    c = NightshiftClient(settings(nightshift_receipt_key_sha256=pin), tracer, transport=httpx.MockTransport(handler_with(meterless)))
    r = c.chat("fast", [{"role": "user", "content": "hi"}], agent="Extractor")
    (event,) = tracer.read()
    return c, r, event


def test_valid_receipt_is_verified(tmp_path):
    c, r, event = call(tmp_path, {"receipt_envelope": envelope()})
    assert r.content == "OK" and r.receipt_verified is True and r.receipt_check == "valid"
    assert event["status"] == "ok" and event["extra"] == {"receipt_verified": True, "receipt_check": "valid"}
    assert "unverified" not in event["output_summary"]
    assert c.receipts_unverified == 0


def test_tampered_receipt_is_unverified_but_not_refused(tmp_path):
    c, r, event = call(tmp_path, {"receipt_envelope": envelope(tamper=True)})
    assert r.content == "OK"  # degraded, not refused
    assert r.receipt_verified is False and r.receipt_check == "bad_signature"
    assert event["status"] == "ok" and "receipt unverified (degraded)" in event["output_summary"]
    assert event["extra"]["receipt_verified"] is False
    assert c.receipts_unverified == 1


def test_missing_receipt_is_unverified_but_not_refused(tmp_path):
    c, r, event = call(tmp_path, None)
    assert r.content == "OK" and r.receipt_id == "rcpt_req_test1"
    assert r.receipt_verified is False and r.receipt_check == "missing"
    assert "receipt unverified (degraded): missing" in event["output_summary"]
    assert c.receipts_unverified == 1


def test_malformed_receipt_is_unverified(tmp_path):
    c, r, _ = call(tmp_path, {"receipt_envelope": {"body": {}, "pubkey_b64": "not base64!", "sig_b64": "x"}})
    assert r.receipt_verified is False and r.receipt_check == "malformed" and c.receipts_unverified == 1


def test_replay_checks_fixture_receipt_and_never_raises(tmp_path):
    fx = tmp_path / "fx"
    fx.mkdir()
    msgs = [{"role": "user", "content": "hi"}]
    from app.adapters.nightshift import fixture_key

    resp = {"id": "chatcmpl-r", "model": "m", "choices": [{"message": {"content": "R"}}]}
    (fx / f"{fixture_key('fast', msgs)}.json").write_text(json.dumps({"lane": "fast", "response": resp}))
    tracer = Tracer("rp", tmp_path, echo=False)
    c = NightshiftClient(settings(sample_mode=True, meterless_runtime_token=""), tracer, fixtures_dir=fx)
    r = c.chat("fast", msgs, agent="Extractor")
    (event,) = tracer.read()
    assert r.replayed and r.content == "R" and r.receipt_verified is False
    assert event["status"] == "replayed" and event["output_summary"] == "replayed, receipt not re-verified"
    assert c.receipts_unverified == 0  # replays never flag a run as degraded


def test_committed_fixture_receipts_still_verify():
    """The sample-mode fixtures' receipts verify, so the judge path's replay notes stay unchanged."""
    from app.config import Settings as S

    folder = S(_env_file=None).sample_dir / "model_fixtures"
    files = sorted(folder.glob("*.json"))
    assert files
    checks = {receipts.verify_response(json.loads(f.read_text(encoding="utf-8"))["response"]) for f in files}
    assert checks == {"valid"}


def test_receipt_from_another_key_is_key_mismatch_but_not_refused(tmp_path):
    """#50: receipts are pinned to Nightshift's key; a correctly signed receipt from any other key is flagged."""
    other = Ed25519PrivateKey.generate()
    c, r, event = call(tmp_path, {"receipt_envelope": envelope(key=other)})
    assert r.content == "OK" and r.receipt_verified is False and r.receipt_check == "key_mismatch"
    assert "receipt unverified (degraded): key_mismatch" in event["output_summary"]
    assert c.receipts_unverified == 1


def test_default_pin_is_the_published_nightshift_key():
    assert Settings(_env_file=None).nightshift_receipt_key_sha256 == receipts.PINNED_KEY_SHA256
    assert receipts.PINNED_KEY_SHA256 == "c9f71fd60dad62bbcb260065a6c4be439dc4997b65785a0e083541b4061c7865"


def test_empty_pin_disables_the_key_check(tmp_path):
    other = Ed25519PrivateKey.generate()
    _, r, _ = call(tmp_path, {"receipt_envelope": envelope(key=other)}, pin="")
    assert r.receipt_verified is True and r.receipt_check == "valid"
