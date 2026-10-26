"""Place the generator's bulk files in Zetaris's internal file store (D-022a), for 01_files.sql.

    python zetaris/stage_files.py --from data/generated --dry-run     # list every copy, sizes, total
    python zetaris/stage_files.py --from data/generated               # copy (docker cp, no restart)

Copies into the running driver container's customer-data volume (shared with the API container):
    /home/zetaris/customer-data/shared/nexus/{ref,cctns,anpr,calls,archive}/
It never starts, stops or restarts a container, and never deletes anything outside nexus/.
Re-running replaces the same files (same names), so it is safe to repeat after a regeneration.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CONTAINER = os.environ.get("ZETARIS_DRIVER_CONTAINER", "zetaris-driver-1")
DEST = "/home/zetaris/customer-data/shared/nexus"

# (source glob relative to the generated dir, destination folder under DEST)
LAYOUT = [
    ("ref/cctv_cameras.csv", "ref"), ("ref/anpr_cameras.csv", "ref"), ("ref/vehicles.csv", "ref"),
    ("ref/releases.csv", "ref"), ("ref/history_sheets.csv", "ref"), ("ref/place_aliases.csv", "ref"),
    ("ref/calendar.csv", "ref"), ("ref/osm_pois.parquet", "ref"),
    ("legacy/cctns_*.csv", "cctns"), ("legacy/archive.parquet", "archive"),
    ("anpr/reads_*.parquet", "anpr"), ("calls/calls_*.parquet", "calls"),
]


# The crime data as files (WS1-19, data/fs_export.py), one folder per nexus_fs table (zetaris/02_fs.sql).
FS_TABLES = ("crimes", "statements", "crime_vehicles", "evidence_media", "forensics", "crime_features_v",
             "tips_v", "section_map", "stations", "link_alerts", "case_bundle_v")


def _fs_dir() -> str:
    """Staging folder for the nexus_fs tables (fs, or fs<suffix>), from the shared source map."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "services" / "api" / "app" / "adapters" / "zetaris_sources.py"
    spec = importlib.util.spec_from_file_location("zetaris_sources", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.sources("files")["fsdir"]


FS_LAYOUT = [(f"fs/{t}/part-0.parquet", f"{_fs_dir()}/{t}") for t in FS_TABLES]


def plan(src: Path, fs: bool = False, only_fs: bool = False) -> list[tuple[Path, str]]:
    out = []
    layout = (FS_LAYOUT if only_fs else LAYOUT + (FS_LAYOUT if fs else []))
    for pattern, folder in layout:
        files = sorted(src.glob(pattern))
        if not files:
            raise SystemExit(f"no files for {pattern} under {src}")
        out += [(f, folder) for f in files]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default="data/generated")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fs", action="store_true", help="also stage the nexus_fs tables from <from>/fs (WS1-19)")
    ap.add_argument("--only-fs", action="store_true", help="stage only the nexus_fs tables")
    a = ap.parse_args()
    items = plan(Path(a.src), a.fs, a.only_fs)
    total = 0
    for f, folder in items:
        total += f.stat().st_size
        print(f"{f.as_posix()} -> {DEST}/{folder}/{f.name}  ({f.stat().st_size / 1024:.0f} KB)")
    print(f"{len(items)} files, {total / 1024 / 1024:.1f} MB -> {CONTAINER}:{DEST}")
    if a.dry_run:
        return 0
    env = os.environ | {"MSYS_NO_PATHCONV": "1"}  # keep Git Bash from rewriting container paths
    with tempfile.TemporaryDirectory() as tmp:  # stage the layout once, then one docker cp
        root = Path(tmp) / "nexus"
        for f, folder in items:
            (root / folder).mkdir(parents=True, exist_ok=True)
            (root / folder / f.name).write_bytes(f.read_bytes())
        subprocess.run(["docker", "cp", f"{root}{os.sep}.", f"{CONTAINER}:{DEST}"], check=True, env=env)
    subprocess.run(["docker", "exec", "-u", "0", CONTAINER, "chmod", "-R", "a+rX", DEST], check=True, env=env)
    print("copied; listing:")
    subprocess.run(["docker", "exec", CONTAINER, "find", DEST, "-type", "f"], check=True, env=env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
