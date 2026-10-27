"""Nightshift compute receipts: the Ed25519 signature check, shared by the live adapter and scripts/verify_receipts.py.

A receipt envelope is {body, pubkey_b64, sig_b64}. `sig_b64` is an Ed25519 signature over `body` as compact JSON
(sorted keys, "," and ":" separators, UTF-8); `pubkey_b64` is the 32-byte public key. A valid signature shows the
body was signed by the holder of that key and not altered since. It does not show the key belongs to Nightshift
(the key travels inside each receipt).

Used at call time in degraded mode only: an unverified receipt is labelled, never refused.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

try:  # pinned in requirements.txt; if it is ever missing, verification degrades instead of crashing the run
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - exercised only on a broken install
    InvalidSignature = Ed25519PublicKey = None  # type: ignore[assignment,misc]

VALID, BAD_SIGNATURE, MALFORMED, MISSING, UNAVAILABLE = "valid", "bad_signature", "malformed", "missing", "unavailable"
KEY_MISMATCH = "key_mismatch"

# The Nightshift receipt-signing public key every receipt seen so far carries: sha256 of the raw 32-byte Ed25519 key
# (logs/receipts_verification.json, 1023 receipts, one key). A receipt with a valid signature from any other key is
# reported as KEY_MISMATCH. Override with NIGHTSHIFT_RECEIPT_KEY_SHA256 (empty = no pin), e.g. after a reinstall.
PINNED_KEY_SHA256 = "c9f71fd60dad62bbcb260065a6c4be439dc4997b65785a0e083541b4061c7865"


def js_number(x: float) -> str:
    """A float exactly as JavaScript's Number.prototype.toString writes it, which is how Nightshift serialises the
    receipt body it signs: shortest round-trip digits, plain decimals from 1e-6 up to (not incl.) 1e21, exponent form
    ("1e-7", "1.5e+21") outside that, and whole numbers without ".0". Python's json writes 1.5e-05 and 1.0 instead,
    so a receipt carrying such a float (the richer receipts since 27 Oct ~21:36) failed as bad_signature."""
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("NaN/Infinity are not JSON")
    if x == 0:
        return "0"
    sign = "-" if x < 0 else ""
    mant, _, exp = repr(abs(x)).partition("e")  # repr = shortest round-trip digits
    whole, _, frac = mant.partition(".")
    raw = whole + frac.rstrip("0") if frac != "0" else whole
    stripped = raw.lstrip("0")
    digits = stripped.rstrip("0")
    n = len(whole) + int(exp or 0) - (len(raw) - len(stripped))  # value = 0.digits x 10^n
    k = len(digits)
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * -n + digits
    else:
        e = n - 1
        out = (digits if k == 1 else digits[0] + "." + digits[1:]) + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + out


def _encode(v: Any) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(str(k), ensure_ascii=False) + ":" + _encode(v[k]) for k in sorted(v)) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_encode(x) for x in v) + "]"
    if isinstance(v, float):
        return js_number(v)
    return json.dumps(v, ensure_ascii=False)  # str, int, bool, None: identical to the signer's output


def canonical(body: dict[str, Any]) -> bytes:
    """The bytes Nightshift signs: the body as compact, key-sorted JSON in UTF-8, numbers written as JavaScript does."""
    return _encode(body).encode("utf-8")


def check_envelope(env: Any, expected_key_sha256: str | None = None) -> str:
    """'valid', 'bad_signature' or 'malformed' for one signed receipt envelope ('unavailable' without cryptography).

    With `expected_key_sha256`, a correctly signed receipt from a different key is 'key_mismatch'."""
    if Ed25519PublicKey is None:
        return UNAVAILABLE
    try:
        pub = base64.b64decode(env["pubkey_b64"], validate=True)
        sig = base64.b64decode(env["sig_b64"], validate=True)
        body = env["body"]
        if len(pub) != 32 or len(sig) != 64 or not isinstance(body, dict):
            return MALFORMED
        key = Ed25519PublicKey.from_public_bytes(pub)
    except (KeyError, TypeError, ValueError):
        return MALFORMED
    try:
        key.verify(sig, canonical(body))
    except InvalidSignature:
        return BAD_SIGNATURE
    if expected_key_sha256 and hashlib.sha256(pub).hexdigest() != expected_key_sha256.strip().lower():
        return KEY_MISMATCH
    return VALID


def envelope_of(data: Any) -> dict[str, Any] | None:
    """The signed envelope inside one chat-completion response (`meterless.receipt_envelope`), if any."""
    if not isinstance(data, dict):
        return None
    env = (data.get("meterless") or {}).get("receipt_envelope") if isinstance(data.get("meterless"), dict) else None
    return env if isinstance(env, dict) else None


def verify_response(data: Any, expected_key_sha256: str | None = None) -> str:
    """Check the receipt carried by one chat-completion response: VALID, BAD_SIGNATURE, MALFORMED, MISSING or
    UNAVAILABLE."""
    env = envelope_of(data)
    return MISSING if env is None else check_envelope(env, expected_key_sha256)
