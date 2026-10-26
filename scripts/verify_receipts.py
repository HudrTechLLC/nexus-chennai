"""Verify the Nightshift compute receipt of every model call Nexus traced (and count calls without one).

    SUPABASE_URL=https://<ref>.supabase.co SUPABASE_SERVICE_ROLE_KEY_FILE=~/.secrets/<key> \
        python scripts/verify_receipts.py [--log <receipts.jsonl>] [--out logs/receipts_verification.json]

What a Nightshift receipt is (read from the receipts themselves; meterless.ai docs could not be reached when
this was written, 27 Oct 2026): every line of the local log (%LOCALAPPDATA%/ai.meterless.runtime/receipts.jsonl,
also served by the runtime at /v1/meterless/receipts) is an envelope {body, pubkey_b64, sig_b64}.
`sig_b64` is an Ed25519 signature over `body` as compact JSON (sorted keys, "," and ":" separators, UTF-8).
`pubkey_b64` is the 32-byte Ed25519 public key. Checking a signature needs only that public key; the private
signing key (receipt-signing.key) is never read.

What this proves, and what it does not: a valid signature shows the receipt was signed by the holder of the
public key printed in the report and has not been altered since. It does NOT show that the key belongs to
Nightshift: the key travels inside each receipt and is not independently published that we could find. The
report states where the key was seen (every log line, the committed fixtures).

Inputs (all read-only):
  - trace_events rows that are model calls (action 'model_call') or cite a receipt id, from Supabase (SELECT only,
    service-role key read from a file path);
  - the local Nightshift receipt log;
  - the receipts embedded in the committed sample-mode fixtures (data/sample/model_fixtures);
  - optionally (--runtime), the runtime's own /v1/meterless/receipts, to confirm it serves the same key. The runtime
    token is read from a file path (METERLESS_RUNTIME_TOKEN_FILE), like the Supabase key.
Buckets are counted separately and never merged. The denominator is every traced model call:
  - live: model calls with status 'ok' (a real Nightshift reply in a live run);
  - degraded: model calls with status 'degraded';
  - replayed_trace: model calls with status 'replayed' (sample mode reusing a recorded reply);
  - model_calls_without_receipt: model calls that carry no receipt id, by status (e.g. 'error': no reply came back);
  - other_events_citing_receipts: non-model-call events (e.g. extract_features) that cite a receipt id, checked too;
  - replayed_fixtures: the receipts inside the committed fixtures (sample mode's recorded replies).
Ids are distinct per bucket. Overlaps (fixture ids among live ids; ids in both live and degraded) are reported.

The output holds counts, ids and the public key only: never a receipt body, prompt text or any secret.
"""

from __future__ import annotations

import argparse
import base64
import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
APP = "nexus-chennai"
FIXTURES = ROOT / "data" / "sample" / "model_fixtures"
DEFAULT_LOG = Path(os.environ.get("LOCALAPPDATA", "")) / "ai.meterless.runtime" / "receipts.jsonl"
DEFAULT_OUT = ROOT / "logs" / "receipts_verification.json"

# =====================
# Signature check
# =====================


def canonical(body: dict[str, Any]) -> bytes:
    """The bytes Nightshift signs: the body as compact, key-sorted JSON in UTF-8."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_envelope(env: Any) -> str:
    """'valid', 'bad_signature' or 'malformed' for one signed receipt envelope."""
    try:
        pub = base64.b64decode(env["pubkey_b64"], validate=True)
        sig = base64.b64decode(env["sig_b64"], validate=True)
        body = env["body"]
        if len(pub) != 32 or len(sig) != 64 or not isinstance(body, dict):
            return "malformed"
        key = Ed25519PublicKey.from_public_bytes(pub)
    except (KeyError, TypeError, ValueError):
        return "malformed"
    try:
        key.verify(sig, canonical(body))
        return "valid"
    except InvalidSignature:
        return "bad_signature"


def request_id(env: dict[str, Any]) -> str | None:
    return ((env.get("body") or {}).get("receipt") or {}).get("request_id")


def find_envelopes(obj: Any) -> Iterable[dict[str, Any]]:
    """Every {body, pubkey_b64, sig_b64} envelope inside a JSON value."""
    if isinstance(obj, dict):
        if {"body", "pubkey_b64", "sig_b64"} <= obj.keys():
            yield obj
        for v in obj.values():
            yield from find_envelopes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from find_envelopes(v)


# =====================
# Inputs
# =====================


def load_log(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Nexus receipts in the Nightshift log, by request id, plus facts about the log."""
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    facts: Counter = Counter()
    keys: Counter = Counter()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            facts["lines"] += 1
            try:
                env = json.loads(line)
            except json.JSONDecodeError:
                facts["unparseable_lines"] += 1
                continue
            keys[env.get("pubkey_b64")] += 1
            status = check_envelope(env)
            facts[f"all_{status}"] += 1
            # The signed bytes must be reproducible from the line itself (guards the canonical form).
            start = line.find('"body":')
            if start >= 0:
                _, end = json.JSONDecoder().raw_decode(line, start + 7)
                facts["canonical_equals_raw" if line[start + 7:end].encode() == canonical(env["body"])
                      else "canonical_differs_from_raw"] += 1
            if (env.get("body", {}).get("receipt") or {}).get("app") != APP:
                facts["other_app"] += 1
                continue
            facts["nexus"] += 1
            rid = request_id(env)
            if rid:
                by_id[rid].append(env)
    facts["nexus_distinct_request_ids"] = len(by_id)
    facts["nexus_request_ids_with_several_receipts"] = sum(1 for v in by_id.values() if len(v) > 1)
    return by_id, {"facts": dict(facts), "keys": dict(keys)}


def load_fixtures(folder: Path) -> list[dict[str, Any]]:
    out = []
    for f in sorted(glob.glob(str(folder / "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out.extend(find_envelopes(json.load(fh)))
    return out


def load_trace(url: str, key: str) -> list[dict[str, Any]]:
    """trace_events rows that are model calls or carry a receipt id. Read-only: GET (SELECT) through PostgREST, nothing else."""
    import httpx

    rows: list[dict[str, Any]] = []
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(base_url=url.rstrip("/") + "/rest/v1", headers=headers, timeout=60) as c:
        offset = 0
        while True:
            r = c.get("/trace_events", params={"select": "receipt_id,status,action",
                                                "or": "(action.eq.model_call,receipt_id.not.is.null)",
                                                "order": "seq", "offset": offset, "limit": 1000})
            if r.status_code != 200:
                raise RuntimeError(f"trace_events read failed: HTTP {r.status_code}")
            page = r.json()
            rows += page
            if len(page) < 1000:
                return rows
            offset += 1000


# =====================
# Report
# =====================


def check_ids(ids: Iterable[str], log: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Each id: found in the Nightshift log, and every receipt for it signature-valid."""
    outcome: dict[str, list[str]] = defaultdict(list)
    receipt_status: Counter = Counter()
    for rid in sorted(set(ids)):
        envs = log.get(rid)
        if not envs:
            outcome["not_in_log"].append(rid)
            continue
        results = {check_envelope(e) for e in envs}
        receipt_status.update(str(e["body"]["receipt"].get("status")) for e in envs)
        if results == {"valid"}:
            outcome["verified"].append(rid)
        elif "malformed" in results:
            outcome["malformed"].append(rid)
        else:
            outcome["bad_signature"].append(rid)
    total = sum(len(v) for v in outcome.values())
    return {
        "ids": total,
        "verified": len(outcome["verified"]),
        "not_in_log": outcome["not_in_log"],
        "bad_signature": outcome["bad_signature"],
        "malformed": outcome["malformed"],
        "nightshift_receipt_status": dict(receipt_status),
    }


def check_fixtures(envs: list[dict[str, Any]], log: dict[str, list[dict[str, Any]]] | None) -> dict[str, Any]:
    status = defaultdict(list)
    for e in envs:
        status[check_envelope(e)].append(request_id(e) or "?")
    out = {"receipts": len(envs), "signature_valid": len(status["valid"]),
           "bad_signature": status["bad_signature"], "malformed": status["malformed"]}
    if log is not None:
        out["also_in_local_log"] = sum(1 for e in envs if request_id(e) in log)
    return out


def claim_text(n_keys: int) -> str:
    """What a verified receipt shows, worded from how many distinct keys were seen."""
    keys = ("every receipt uses the same key (fingerprint below)" if n_keys == 1
            else f"the receipts use {n_keys} different keys (listed below)")
    return (f"Signatures verify against the receipt's embedded Ed25519 public key, and {keys}: each verified receipt "
            "was signed by the holder of its key and is unaltered since. The key ships inside the receipts; we found "
            "no separately published copy (meterless.ai docs unreachable when written), so this does not by itself "
            "prove whose key it is.")


def build_report(trace: list[dict[str, Any]] | None, log: dict[str, list[dict[str, Any]]] | None,
                 log_info: dict[str, Any] | None, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    keys = Counter(e["pubkey_b64"] for e in fixtures)
    if log_info:
        keys.update(log_info["keys"])
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": ("Ed25519 signature over the receipt body as compact key-sorted UTF-8 JSON, checked with the public "
                   "key carried in each receipt. No private key is read."),
        "claim": claim_text(len(keys)),
        "note": ("The replayed fixtures (data/sample/model_fixtures, committed) carry the synthetic prompt previews "
                 "inside their signed receipt bodies; they are kept as recorded, since removing them would break the "
                 "signatures. This report itself holds no receipt body or prompt text."),
        "public_keys": [{"pubkey_b64": k, "sha256": hashlib.sha256(base64.b64decode(k)).hexdigest(), "receipts": n}
                        for k, n in keys.most_common()],
        "replayed_fixtures": check_fixtures(fixtures, log),
    }
    if log_info is not None:
        report["nightshift_log"] = log_info["facts"]
    if trace is not None and log is not None:
        buckets: dict[str, set[str]] = defaultdict(set)
        without: Counter = Counter()
        calls = [r for r in trace if r.get("action", "model_call") == "model_call"]
        for r in calls:
            if not r["receipt_id"]:
                without[r["status"]] += 1
                continue
            name = {"ok": "live", "degraded": "degraded", "replayed": "replayed_trace"}.get(r["status"], f"other:{r['status']}")
            buckets[name].add(r["receipt_id"])
        citing = {r["receipt_id"] for r in trace if r.get("action", "model_call") != "model_call" and r["receipt_id"]}
        with_receipt = [r for r in calls if r["receipt_id"]]
        distinct = {r["receipt_id"] for r in with_receipt}
        report["trace_model_calls"] = {"rows": len(calls), "rows_with_receipt": len(with_receipt),
                                       "distinct_receipt_ids": len(distinct),
                                       "rows_repeating_an_id": len(with_receipt) - len(distinct)}
        for name in ("live", "degraded", "replayed_trace"):
            report[name] = check_ids(buckets.get(name, set()), log)
        report["model_calls_without_receipt"] = dict(without)
        others = {k: len(v) for k, v in buckets.items() if k.startswith("other:")}
        if others:
            report["other_status_ids"] = others
        report["other_events_citing_receipts"] = {**check_ids(citing, log),
                                                  "also_a_live_model_call": len(citing & buckets.get("live", set()))}
        fixture_ids = {request_id(e) for e in fixtures}
        report["overlap_fixture_and_live_ids"] = sorted(fixture_ids & buckets.get("live", set()))
        report["overlap_live_and_degraded_ids"] = sorted(buckets.get("live", set()) & buckets.get("degraded", set()))
    return report


def runtime_keys(base: str, token: str, limit: int = 50) -> dict[str, Any]:
    """The keys on the runtime's own receipt feed, and whether those receipts verify. Read-only GET."""
    import httpx

    r = httpx.get(base.rstrip("/") + "/v1/meterless/receipts", params={"limit": limit},
                  headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"/v1/meterless/receipts: HTTP {r.status_code}")
    envs = list(find_envelopes(r.json()))
    keys = Counter(e.get("pubkey_b64") for e in envs)
    return {"endpoint": "/v1/meterless/receipts", "receipts_read": len(envs),
            "signature_valid": sum(check_envelope(e) == "valid" for e in envs),
            "keys": [{"sha256": hashlib.sha256(base64.b64decode(k)).hexdigest(), "receipts": n} for k, n in keys.items()]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Nightshift receipts.jsonl")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--fixtures-only", action="store_true", help="only the committed fixtures (no log, no Supabase)")
    ap.add_argument("--runtime", default="", help="runtime base URL (e.g. http://127.0.0.1:8088) to compare its key")
    a = ap.parse_args(argv)
    key = token = ""
    try:
        fixtures = load_fixtures(FIXTURES)
        trace = log = log_info = None
        if not a.fixtures_only:
            key_file = os.environ.get("SUPABASE_SERVICE_ROLE_KEY_FILE", "")
            url = os.environ.get("SUPABASE_URL", "")
            if not key_file or not url:
                raise SystemExit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY_FILE (a path), or use --fixtures-only.")
            key = Path(os.path.expanduser(key_file)).read_text(encoding="utf-8").strip()
            log, log_info = load_log(a.log)
            trace = load_trace(url, key)
        report = build_report(trace, log, log_info, fixtures)
        if a.runtime:
            tf = os.environ.get("METERLESS_RUNTIME_TOKEN_FILE", "")
            if not tf:
                raise SystemExit("--runtime needs METERLESS_RUNTIME_TOKEN_FILE (a path).")
            token = Path(os.path.expanduser(tf)).read_text(encoding="utf-8").strip()
            rt = runtime_keys(a.runtime, token)
            rt["same_key_as_log"] = [k["sha256"] for k in rt["keys"]] == [k["sha256"] for k in report["public_keys"]]
            report["runtime_feed"] = rt
    except SystemExit:
        raise
    except Exception as exc:  # type and message only: never the client, its headers or the key
        msg = str(exc)
        for secret in (key, token):
            if secret:
                msg = msg.replace(secret, "<redacted>")
        print(f"verify_receipts failed: {type(exc).__name__}: {msg[:300]}", file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fx = report["replayed_fixtures"]
    print(f"replayed fixtures: {fx['signature_valid']}/{fx['receipts']} signatures valid")
    if "trace_model_calls" in report:
        t = report["trace_model_calls"]
        print(f"traced model calls: {t['rows']} rows, {t['rows_with_receipt']} with a receipt id "
              f"({t['distinct_receipt_ids']} distinct); without a receipt id: {report['model_calls_without_receipt'] or 0}")
    for name in ("live", "degraded", "replayed_trace", "other_events_citing_receipts"):
        if name in report:
            b = report[name]
            print(f"{name}: {b['verified']}/{b['ids']} distinct ids found in the Nightshift log with a valid signature"
                  f" (not in log {len(b['not_in_log'])}, bad signature {len(b['bad_signature'])},"
                  f" malformed {len(b['malformed'])})")
    if "runtime_feed" in report:
        rt = report["runtime_feed"]
        print(f"runtime feed: {rt['signature_valid']}/{rt['receipts_read']} valid, same key as the log: {rt['same_key_as_log']}")
    print(f"public key sha256: {', '.join(k['sha256'] for k in report['public_keys'])}")
    print(f"wrote {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
