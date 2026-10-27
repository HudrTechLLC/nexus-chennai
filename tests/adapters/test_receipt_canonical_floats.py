"""Receipt canonical form writes numbers as JavaScript does (Nightshift's signer).

Regression for 27 Oct ~23:04 IST: Nightshift's richer receipts carry small floats ("naive_usd":0.000015). Python's json
wrote 1.5e-05, the signed bytes differed and every new live receipt read bad_signature (a false "receipts unverified"
warning on live alerts). The fixture is a real new-schema receipt from a one-word ops check ("Reply with the single
word OK."): stored whole, because any redaction of a signed body breaks its signature; it holds no secret.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app import receipts

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nightshift_receipt_v1_floats.json"


def real_receipt() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_a_real_new_schema_receipt_with_small_floats_is_valid():
    env = real_receipt()
    assert env["body"]["receipt"]["cost"]["naive_usd"] == 1.5e-05  # the float that broke it
    assert receipts.check_envelope(env) == receipts.VALID
    assert receipts.check_envelope(env, receipts.PINNED_KEY_SHA256) == receipts.VALID
    assert b'"naive_usd":0.000015' in receipts.canonical(env["body"])


def test_the_real_receipt_tampered_is_bad_signature():
    env = real_receipt()
    bad = copy.deepcopy(env)
    bad["body"]["receipt"]["cost"]["naive_usd"] = 2.5e-05
    assert receipts.check_envelope(bad) == receipts.BAD_SIGNATURE


def test_the_real_receipt_through_a_chat_response_is_valid():
    assert receipts.verify_response({"meterless": {"receipt_envelope": real_receipt()}}) == receipts.VALID


@pytest.mark.parametrize("x,js", [
    (1.5e-05, "0.000015"), (1e-6, "0.000001"), (1e-7, "1e-7"), (2.5e-8, "2.5e-8"), (-2.5e-8, "-2.5e-8"),
    (1e21, "1e+21"), (1.2345e22, "1.2345e+22"), (1e20, "100000000000000000000"), (0.1 + 0.2, "0.30000000000000004"),
    (1.0, "1"), (-0.0, "0"), (0.0, "0"), (123.456, "123.456"), (0.5, "0.5"), (0.18, "0.18"), (100.25, "100.25"),
])
def test_float_edge_cases_match_javascript(x, js):
    assert receipts.js_number(x) == js


def test_ints_strings_and_unicode_are_unchanged():
    body = {"b": 1, "a": [True, None, "Ä · x"], "c": {"z": 10**18, "y": "q\"t"}}
    assert receipts.canonical(body) == json.dumps(body, sort_keys=True, separators=(",", ":"),
                                                  ensure_ascii=False).encode("utf-8")


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        receipts.js_number(float("nan"))
