"""Build the fixed MO IDF table for similar-MO scoring (WS2-21, D-027 fallback). Owner: nexus-2.

    cd services/api
    python -m app.engines.mo_idf --source sample             # data/sample/sb/crime_features.parquet
    python -m app.engines.mo_idf --source live               # every row of sb.crime_features_v via Zetaris

Writes cities/<city>/mo_idf.json: the smoothed IDF of every field-tagged MO key (`approach=snatch`,
`tag=red_bike`, ...) over all extracted MO records, plus a stamp saying which corpus it came from. It reads no
labels and no truth, so it cannot leak the evaluation's answers. The Linker loads the table only when
NEXUS_MO_TFIDF is on (default off). Regenerate after a re-extraction; the stamp shows which one it reflects.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT, get_settings
from .similarity import build_mo_idf

VERSION = 1


def table_path(city: str | None = None, root: Path = REPO_ROOT) -> Path:
    return root / "cities" / (city or get_settings().city) / "mo_idf.json"


def _json(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _records(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], Counter]:
    """(crime_id, extractor_version, mo, visual_tags) rows -> feature dicts, and the version counts."""
    out, versions = [], Counter()
    for _cid, version, mo, tags in rows:
        versions[str(version)] += 1
        out.append({"mo": _json(mo) or {}, "visual_tags": _json(tags) or []})
    return out, versions


SELECT = "SELECT crime_id, extractor_version, mo, visual_tags FROM {src} ORDER BY crime_id"


def sample_rows(sample_dir: Path) -> list[list[Any]]:
    import duckdb

    src = f"read_parquet('{(sample_dir / 'sb' / 'crime_features.parquet').as_posix()}')"
    return [list(r) for r in duckdb.sql(SELECT.format(src=src)).fetchall()]


def live_rows() -> list[list[Any]]:
    import uuid

    from ..adapters.zetaris import ZetarisClient

    z = ZetarisClient(get_settings())
    try:  # ORDER BY above the scan: D-031
        return z._post(SELECT.format(src="sb.crime_features_v"), str(uuid.uuid4()), 100000, 300)
    finally:
        z.close()


def build(rows: list[list[Any]], source: str) -> dict[str, Any]:
    records, versions = _records(rows)
    table = build_mo_idf(records)
    return {"version": VERSION, "source": source, "extractor_versions": dict(sorted(versions.items())),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **table}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build cities/<city>/mo_idf.json")
    ap.add_argument("--source", choices=("sample", "live"), required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rows = sample_rows(get_settings().sample_dir) if args.source == "sample" else live_rows()
    src = "data/sample/sb/crime_features.parquet" if args.source == "sample" else "zetaris sb.crime_features_v"
    table = build(rows, src)
    out = args.out or table_path()
    out.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}: {table['docs']} records, {len(table['idf'])} keys, versions {table['extractor_versions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
