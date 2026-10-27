"""Which trace completion ids are matched to a signed Nightshift receipt, for the web console.

Reads Nightshift's receipts log (the same file and the same signature check as scripts/verify_receipts.py) and a
list of trace `receipt_id`s, and writes logs/receipt_matches.json (copied into the web build by
apps/web/scripts/sync-docs.mjs): the ids whose every receipt in the log
carries a valid Ed25519 signature from the pinned key. Ids only: no receipt body, prompt or key is written.

    python scripts/receipt_matches.py --ids ids.json          # ids.json: ["chatcmpl-…", …] or {"rows": [{"receipt_id": …}]}
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import verify_receipts as v

OUT = v.ROOT / "logs" / "receipt_matches.json"


def ids_from(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows", []) if isinstance(data, dict) else data
    return sorted({(r.get("receipt_id") if isinstance(r, dict) else r) for r in rows} - {None, ""})


def build(ids: list[str], log: dict) -> dict:
    result = v.check_ids(ids, log)
    verified = sorted(set(ids) - set(result["not_in_log"]) - set(result["bad_signature"])
                      - set(result["malformed"]) - set(result["key_mismatch"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Each id is looked up by request_id in Nightshift's receipts log; every receipt for it must carry a "
                  "valid Ed25519 signature from the pinned key (scripts/verify_receipts.py).",
        "checked": len(ids),
        "verified": len(verified),
        "not_verified": len(ids) - len(verified),
        "ids": verified,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids", type=Path, required=True)
    ap.add_argument("--log", type=Path, default=v.DEFAULT_LOG)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    log, _ = v.load_log(a.log)
    report = build(ids_from(a.ids), log)
    a.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{report['verified']}/{report['checked']} ids matched to a signed Nightshift receipt -> {a.out}")
    return 0 if report["checked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
