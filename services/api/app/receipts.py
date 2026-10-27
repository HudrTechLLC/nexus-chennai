"""Nightshift compute receipts: the Ed25519 signature check, shared by the live adapter and scripts/verify_receipts.py.

A receipt envelope is {body, pubkey_b64, sig_b64}. `sig_b64` is an Ed25519 signature over `body` as compact JSON
(sorted keys, "," and ":" separators, UTF-8); `pubkey_b64` is the 32-byte public key. A valid signature shows the
body was signed by the holder of that key and not altered since. It does not show the key belongs to Nightshift
(the key travels inside each receipt).

Used at call time in degraded mode only: an unverified receipt is labelled, never refused.
"""

from __future__ import annotations

import base64
import json
from typing import Any

try:  # pinned in requirements.txt; if it is ever missing, verification degrades instead of crashing the run
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - exercised only on a broken install
    InvalidSignature = Ed25519PublicKey = None  # type: ignore[assignment,misc]

VALID, BAD_SIGNATURE, MALFORMED, MISSING, UNAVAILABLE = "valid", "bad_signature", "malformed", "missing", "unavailable"


def canonical(body: dict[str, Any]) -> bytes:
    """The bytes Nightshift signs: the body as compact, key-sorted JSON in UTF-8."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_envelope(env: Any) -> str:
    """'valid', 'bad_signature' or 'malformed' for one signed receipt envelope ('unavailable' without cryptography)."""
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
        return VALID
    except InvalidSignature:
        return BAD_SIGNATURE


def envelope_of(data: Any) -> dict[str, Any] | None:
    """The signed envelope inside one chat-completion response (`meterless.receipt_envelope`), if any."""
    if not isinstance(data, dict):
        return None
    env = (data.get("meterless") or {}).get("receipt_envelope") if isinstance(data.get("meterless"), dict) else None
    return env if isinstance(env, dict) else None


def verify_response(data: Any) -> str:
    """Check the receipt carried by one chat-completion response: VALID, BAD_SIGNATURE, MALFORMED, MISSING or
    UNAVAILABLE."""
    env = envelope_of(data)
    return MISSING if env is None else check_envelope(env)
