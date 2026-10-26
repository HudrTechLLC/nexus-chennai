"""Redaction for trace rows copied to Supabase (DECISIONS D-025).

The JSONL trace stays exactly as written (R3). The copy that the console reads passes this
step first: secrets are masked, tip and search text is cut short, and every summary is
capped. Ids that judges need (run, alert, crime, query ids) are kept.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_SUMMARY = 500
MAX_PUBLIC_TEXT = 60  # tip or search text: enough to recognise, never the whole thing

_SECRETS = (
    re.compile(r"nvapi-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"sb_(?:secret|publishable)_[A-Za-z0-9_-]{6,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*"),  # JWTs
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    # Passphrases and passwords can contain spaces: mask to the end of the clause.
    re.compile(r"(?i)\b(?:password|passphrase|tip_code)\b\s*[:=]\s*[^;\n]+"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret)\b\s*[:=]\s*\S+"),
    re.compile(r"argon2id?\$[^\s'\"]+"),
    # Long opaque strings (keys), but not UUIDs or the readable ids Nexus uses.
    re.compile(r"\b(?![0-9a-f]{8}-[0-9a-f]{4}-)[A-Za-z0-9_]{40,}\b"),
)
_PUBLIC_TEXT_AGENTS = ("Tip Guard", "Scout Intent")
_PUBLIC_TEXT_ACTIONS = ("screen_tip", "quarantine_query", "classify", "tip")


def mask(text: str | None) -> str | None:
    if text is None:
        return None
    out = str(text)
    for p in _SECRETS:
        out = p.sub("[redacted]", out)
    return out


def _cut(text: str | None, n: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= n else text[: n - 1] + "…"


def redact_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """A trace event safe to store for the console."""
    e = dict(event)
    public_text = e.get("agent_name") in _PUBLIC_TEXT_AGENTS or any(
        a in str(e.get("action") or "") for a in _PUBLIC_TEXT_ACTIONS)
    for key in ("input_summary", "output_summary"):
        v = mask(e.get(key))
        e[key] = _cut(v, MAX_PUBLIC_TEXT if public_text and key == "input_summary" else MAX_SUMMARY)
    if isinstance(e.get("extra"), Mapping):
        e["extra"] = {k: (_cut(mask(v), MAX_SUMMARY) if isinstance(v, str) else v) for k, v in e["extra"].items()
                      if not re.search(r"(?i)key|token|secret|password|passphrase", str(k))}
    return e
