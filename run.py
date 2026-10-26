"""Start the Nexus API, optionally running one input through POST /run.

    python run.py                          # serve on :8000
    python run.py --once input_examples/example_1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "services" / "api"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--once", type=Path, help="run one input JSON through /run and print the result")
    args = ap.parse_args()

    if args.once:
        # UTF-8 whatever the console code page: `run.py --once x.json > out.json 2> trace.log` on Windows
        # would otherwise write cp1252 (an en dash as byte 0x96) and the result would not parse as JSON.
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        # Keep stdout = the JSON result only (pipe-friendly); trace lines go to stderr and logs/.
        os.environ.setdefault("NEXUS_TRACE_STREAM", "stderr")

    from app.config import get_settings

    port = args.port or get_settings().port
    if args.once:
        from fastapi.testclient import TestClient

        from app.main import app

        body = json.loads(args.once.read_text(encoding="utf-8"))
        resp = TestClient(app).post("/run", json=body)
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        return 0 if resp.status_code == 200 else 1

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
