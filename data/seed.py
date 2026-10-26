"""Load data/generated/supabase/*.jsonl into Supabase (WS1-10). Idempotent; run from merged main.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python -m data.seed [--in data/generated] [--dry-run]

- One transaction for everything: either all of it lands or none.
- Upserts by primary key, so re-running refreshes rows (and fills placeholder stations).
- Child rows without their own stable key (crime_vehicles) are replaced per crime.
- Never touches profiles, auth or any table this lane does not own.
Rows go in via COPY into a jsonb staging table, then jsonb_populate_record into the real
table, so column types come from the schema itself.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# (file, table, key, columns, extra SQL for geometry columns)
TABLES = [
    ("stations", "stations", "station_id",
     ["station_id", "name", "type", "zone", "district", "region", "synthetic"],
     {"geom": "extensions.st_multi(extensions.st_setsrid(extensions.st_geomfromgeojson(doc->>'geom'), 4326))",
      "centroid": "extensions.st_setsrid(extensions.st_geomfromgeojson(doc->>'centroid'), 4326)"}),
    ("wards", "wards", "ward_no", ["ward_no", "name", "zone"],
     {"geom": "extensions.st_multi(extensions.st_setsrid(extensions.st_geomfromgeojson(doc->>'geom'), 4326))"}),
    ("crimes", "crimes", "crime_id",
     ["crime_id", "source", "source_row_id", "station_id", "fir_no", "category", "sub_type", "sections",
      "occurred_from", "occurred_to", "reported_at", "lat", "lon", "address", "ward_no", "h3_r9", "h3_r8",
      "geohash7", "week", "severity", "property", "weapon", "offenders_described", "victims", "status",
      "narrative", "synthetic"], {}),
    ("statements", "statements", "statement_id",
     ["statement_id", "crime_id", "witness_ref", "mode", "text", "audio_path", "transcript_model", "recorded_at",
      "source", "source_row_id", "synthetic"], {}),
]


def _load(cur, path: Path) -> int:
    cur.execute("truncate _stage")
    with cur.copy("copy _stage (doc) from stdin") as cp:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                cp.write_row((line,))
    cur.execute("select count(*) from _stage")
    return cur.fetchone()[0]


def _upsert(cur, table: str, key: str, cols: list[str], geo: dict[str, str]) -> None:
    all_cols = cols + list(geo)
    sel = [f"(r).{c}" for c in cols] + list(geo.values())
    updates = ", ".join(f"{c} = excluded.{c}" for c in all_cols if c != key)
    cur.execute(
        f"insert into public.{table} ({', '.join(all_cols)}) "
        f"select {', '.join(sel)} from (select doc, jsonb_populate_record(null::public.{table}, doc) r from _stage) s "
        f"on conflict ({key}) do update set {updates}")


def seed(src: Path, dry_run: bool) -> None:
    from db_migrate import connect  # same pooler logic and password handling as migrations

    sb = src / "supabase"
    with connect() as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("set local search_path = public, extensions")
            cur.execute("create temp table _stage (doc jsonb) on commit drop")
            for fname, table, key, cols, geo in TABLES:
                n = _load(cur, sb / f"{fname}.jsonl")
                _upsert(cur, table, key, cols, geo)
                print(f"{table}: {n} rows upserted")
            # section_map has a nullable natural key, so refresh it whole (nothing references it).
            n = _load(cur, sb / "section_map.jsonl")
            cur.execute("delete from public.section_map")
            cur.execute("insert into public.section_map (ipc_code, bns_code, title, category_group, source, verified) "
                        "select (r).ipc_code, (r).bns_code, (r).title, (r).category_group, (r).source, (r).verified "
                        "from (select jsonb_populate_record(null::public.section_map, doc) r from _stage) s")
            print(f"section_map: {n} rows")
            # crime_vehicles: replace per crime (identity key).
            n = _load(cur, sb / "crime_vehicles.jsonl")
            cur.execute("delete from public.crime_vehicles v using (select distinct doc->>'crime_id' cid from _stage) s "
                        "where v.crime_id = s.cid")
            cur.execute("insert into public.crime_vehicles (crime_id, role, vehicle_type, plate_pattern, make_model, "
                        "colour, synthetic) select (r).crime_id, (r).role, (r).vehicle_type, (r).plate_pattern, "
                        "(r).make_model, (r).colour, (r).synthetic "
                        "from (select jsonb_populate_record(null::public.crime_vehicles, doc) r from _stage) s")
            print(f"crime_vehicles: {n} rows")
            cur.execute("select count(*) from public.crimes where synthetic")
            print(f"crimes in db (synthetic): {cur.fetchone()[0]}")
            if dry_run:
                raise _DryRun()


class _DryRun(Exception):
    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--dry-run", action="store_true", help="run everything, then roll back")
    a = ap.parse_args()
    if not os.environ.get("NEXUS_DB_PASSWORD"):
        sys.exit("NEXUS_DB_PASSWORD is not set (read it from the password file for this command only)")
    try:
        seed(Path(a.src), a.dry_run)
    except _DryRun:
        print("dry run: rolled back")


if __name__ == "__main__":
    main()
