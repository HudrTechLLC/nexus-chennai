"""Export the two model-output fixtures the generator cannot make (WS1-19). Owner: nexus-1.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python -m data.fixtures.export

`python -m data.setup_live` loads these into a judge's Zetaris, so live mode needs no Supabase:

- crime_features_v.parquet: the Extractor's MO features (Nightshift output), one row per generator crime,
  in the exact columns and text forms of the sb.crime_features_v datasource view, plus `bundle_json`, the
  exact `features` text sb.case_bundle_v builds for that row. The Extractor reuses them through q_features,
  so a judge's machine does not re-extract all of them.
- tip_verdicts.parquet: Tip Guard's verdict (`guard`) and the resulting `status` for each generator tip.
  q_tip_corroboration filters on status, so without these, tips find nothing on the file path.

Only generator rows are exported (crimes whose source_row_id is uuid5(GEN_NS, crime_id)); console FIRs stay
in our database. MANIFEST.json records the counts, extractor versions and the commit the export ran from.
Every row is synthetic (rule R9).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

GEN_NS = "6f1c2a52-6a71-4c51-9e57-2c7b1b0a0e42"  # data/seed.py GEN_NS

FEATURES_SQL = f"""
select cf.crime_id, cf.extractor_version, cf.mo::text, array_to_json(cf.visual_tags)::text, cf.entities::text,
       cf.model, cf.receipt_id, cf.confidence, (cf.reviewed_by is not null), cf.synthetic,
       json_build_object('extractor_version', cf.extractor_version, 'model', cf.model, 'receipt_id', cf.receipt_id,
         'mo', cf.mo, 'visual_tags', to_json(cf.visual_tags), 'entities', cf.entities, 'confidence', cf.confidence,
         'reviewed_by_officer', cf.reviewed_by is not null)::text
from public.crime_features cf join public.crimes c on c.crime_id = cf.crime_id
where c.source_row_id::text = extensions.uuid_generate_v5('{GEN_NS}'::uuid, c.crime_id)::text
order by cf.crime_id, cf.extractor_version
"""
FEATURES_COLUMNS = [("crime_id", "VARCHAR"), ("extractor_version", "VARCHAR"), ("mo", "VARCHAR"),
                    ("visual_tags", "VARCHAR"), ("entities", "VARCHAR"), ("model", "VARCHAR"),
                    ("receipt_id", "VARCHAR"), ("confidence", "FLOAT"), ("reviewed_by_officer", "BOOLEAN"),
                    ("synthetic", "BOOLEAN"), ("bundle_json", "VARCHAR")]

TIPS_SQL = "select tip_id, guard::text, status from public.tips where tip_id = any(%s) order by tip_id"
TIPS_COLUMNS = [("tip_id", "VARCHAR"), ("guard", "VARCHAR"), ("status", "VARCHAR")]


def _write(rows: list[tuple], cols: list[tuple[str, str]], path: Path) -> None:
    import duckdb

    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({', '.join(f'{c} {t}' for c, t in cols)})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})", rows)
    con.execute(f"COPY (SELECT * FROM t ORDER BY 1, 2) TO '{path.as_posix()}' (FORMAT PARQUET)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(HERE))
    ap.add_argument("--gen", default=str(ROOT / "data" / "generated"), help="generator output: which tips are ours")
    a = ap.parse_args()
    from db_migrate import connect

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(FEATURES_SQL)
        feats = cur.fetchall()
        ids = [json.loads(ln)["tip_id"] for ln in (Path(a.gen) / "supabase" / "tips.jsonl").open(encoding="utf-8")]
        cur.execute(TIPS_SQL, (ids,))
        tips = cur.fetchall()
    _write(feats, FEATURES_COLUMNS, out / "crime_features_v.parquet")
    _write(tips, TIPS_COLUMNS, out / "tip_verdicts.parquet")
    versions: dict[str, int] = {}
    for r in feats:
        versions[r[1]] = versions.get(r[1], 0) + 1
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": commit,
                "crime_features": len(feats), "extractor_versions": dict(sorted(versions.items())),
                "tips": len(tips), "tip_status": {s: sum(1 for t in tips if t[2] == s) for s in sorted({t[2] for t in tips})},
                "synthetic": True}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
