"""Set up LIVE mode on your own Zetaris, with no Supabase (WS1-19).

    ZETARIS_API_KEY_FILE=~/path/to/key python -m data.setup_live

Needs: a local Zetaris in Docker (as the Participant Setup Guide sets up) and its API key in an environment
variable (ZETARIS_API_KEY_FILE, a path to the key file). ZETARIS_REST_URL, ZETARIS_ORG_ID and
ZETARIS_DRIVER_CONTAINER have defaults (http://localhost:8888/api/v1.0, 1, zetaris-driver-1).

Steps (each is also a command of its own):
1. `python -m data.generator`              the deterministic synthetic city (seed 42) -> data/generated
2. `python -m data.generator.stills`        the synthetic CCTV stills and their evidence rows
3. `python -m data.fs_export`              the crime data as Parquet with the sb shapes -> data/generated/fs,
                                           plus the committed model-output fixtures (data/fixtures)
4. `python zetaris/stage_files.py --fs`    copy every file into the Zetaris file store (docker cp)
5. `python zetaris/register.py --data files`  register the file tables and the views (container nexusfs)
6. a smoke test: q_ping, then the hero case and its candidates through the named queries

Then start the API with ZETARIS_DATA=files. Nothing generated is committed; re-running is safe (register.py
skips objects that already exist, and stage_files overwrites the same files).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERO = "CHN-AD-2026-001182"


def _run(cmd: list[str], dry: bool) -> None:
    print("$ " + " ".join(cmd), flush=True)
    if not dry:
        subprocess.run(cmd, check=True, cwd=ROOT)


def smoke() -> None:
    sys.path.insert(0, str(ROOT / "services" / "api"))
    from app.adapters.zetaris import ZetarisClient
    from app.config import get_settings

    s = get_settings().model_copy(update={"zetaris_data": "files", "sample_mode": False})
    z = ZetarisClient(s)
    try:
        z.named("q_ping", agent="setup")
        case = z.named("q_case", agent="setup", crime_id=HERO)
        cands = z.named("q_candidates", agent="setup", crime_id=HERO, days=45, ring=6)
    finally:
        z.close()
    if not case.rows:
        raise SystemExit(f"smoke test failed: {HERO} not found through nexus_fs")
    print(f"smoke: q_case {HERO} ok, {len(cands.rows)} candidates, via {case.source}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Set up live mode on your own Zetaris, no Supabase (WS1-19)")
    ap.add_argument("--dry-run", action="store_true", help="print the steps and the SQL, change nothing")
    ap.add_argument("--skip-generate", action="store_true", help="reuse data/generated (steps 1-2)")
    a = ap.parse_args()
    py = sys.executable
    gen = ROOT / "data" / "generated"
    if not a.dry_run and not os.environ.get("ZETARIS_API_KEY_FILE"):
        raise SystemExit("Set ZETARIS_API_KEY_FILE to the path of your Zetaris API key file first.")
    if not a.skip_generate:
        _run([py, "-m", "data.generator", "--out", str(gen)], a.dry_run)
        _run([py, "-m", "data.generator.stills", "--from", str(gen)], a.dry_run)
    _run([py, "-m", "data.fs_export", "--from", str(gen)], a.dry_run)
    _run([py, "zetaris/stage_files.py", "--from", str(gen), "--fs"], a.dry_run)
    _run([py, "zetaris/register.py", "--data", "files"] + (["--dry-run"] if a.dry_run else []), False)
    if a.dry_run:
        return
    smoke()
    print("\nLive data is ready. Start the API with:\n    ZETARIS_DATA=files  (plus your Zetaris and Nightshift settings)")


if __name__ == "__main__":
    main()
