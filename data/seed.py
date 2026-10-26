"""Load data/generated/supabase/*.jsonl into Supabase (WS1-10). Idempotent; run from merged main.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" python -m data.seed [--in data/generated] [--dry-run]

- One transaction for everything: either all of it lands or none.
- Upserts by primary key, so re-running refreshes rows (and fills placeholder stations).
- Child rows without their own stable key (crime_vehicles) are replaced per crime.
- Never touches profiles, auth or any table this lane does not own.
- Crimes the generator did not make (e.g. FIRs filed from the console) are never retired or
  overwritten; a generated crime that would take one's crime_id or FIR number stops the seed.
Rows go in via COPY into a jsonb staging table, then jsonb_populate_record into the real
table, so column types come from the schema itself.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
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
    ("persons", "persons", "person_id",
     ["person_id", "name", "aliases", "descriptors", "residence_ward", "source", "source_row_id", "synthetic"], {}),
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


# Generator rows carry source_row_id = uuid5(GEN_NS, crime_id); see data/generator/cli.py.
GEN_NS = uuid.UUID("6f1c2a52-6a71-4c51-9e57-2c7b1b0a0e42")


def _foreign_crimes(cur) -> dict[str, tuple[str, str]]:
    """Crimes in the database the generator did not make: crime_id -> (station_id, fir_no)."""
    cur.execute("select crime_id, station_id, fir_no, source_row_id from public.crimes")
    return {cid: (st, fir) for cid, st, fir, srid in cur.fetchall() if srid != str(uuid.uuid5(GEN_NS, cid))}


def _guard_foreign(cur, foreign: dict[str, tuple[str, str]]) -> None:
    """Runs with _stage = crimes. Refuses to overwrite a crime the generator did not make."""
    cur.execute("select doc->>'crime_id', doc->>'station_id', doc->>'fir_no' from _stage")
    keys = {v: k for k, v in foreign.items()}
    clash = [(cid, st, fir) for cid, st, fir in cur.fetchall() if cid in foreign or (st, fir) in keys]
    if clash:
        raise RuntimeError(f"{len(clash)} generated crimes would overwrite crimes filed outside the generator "
                           f"(e.g. {clash[:3]}); regenerate or renumber before seeding; rolling back")


def _retire_stale_crimes(cur, allow: bool, keep: list[str]) -> None:
    """Synthetic crimes no longer generated (e.g. renumbered) are removed. Extracted features
    are first moved to the regenerated crime with identical content (station, time, sub-type,
    narrative), so a re-seed never throws away Extractor work. Runs with _stage = crimes."""
    cur.execute("create temp table _new_ids on commit drop as select doc->>'crime_id' as crime_id from _stage")
    cur.execute("create temp table _stale on commit drop as select crime_id from public.crimes "
                "where synthetic and crime_id not in (select crime_id from _new_ids) and crime_id <> all(%s)", (keep,))
    cur.execute("select count(*) from _stale")
    stale = cur.fetchone()[0]
    if stale and not allow:
        raise RuntimeError(f"{stale} seeded crimes are no longer generated; a re-seed must be additive "
                           "(rerun with --retire only if retiring them is agreed); rolling back")
    cur.execute(
        "update public.crime_features cf set crime_id = n.crime_id "
        "from public.crimes o join public.crimes n on n.station_id = o.station_id "
        "and n.occurred_from = o.occurred_from and n.sub_type is not distinct from o.sub_type "
        "and n.narrative is not distinct from o.narrative and n.crime_id <> o.crime_id "
        "where cf.crime_id = o.crime_id and o.crime_id in (select crime_id from _stale) "
        "and n.crime_id in (select crime_id from _new_ids) "
        "and not exists (select 1 from public.crime_features x where x.crime_id = n.crime_id)")
    moved = cur.rowcount
    cur.execute("delete from public.crimes where crime_id in (select crime_id from _stale)")
    print(f"crimes: retired {cur.rowcount} stale synthetic rows; moved {moved} crime_features to new ids")


def seed(src: Path, dry_run: bool, retire: bool = False) -> None:
    from db_migrate import connect  # same pooler logic and password handling as migrations

    sb = src / "supabase"
    with connect() as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("set local search_path = public, extensions")
            cur.execute("create temp table _stage (doc jsonb) on commit drop")
            foreign = _foreign_crimes(cur)
            if foreign:
                print(f"crimes: {len(foreign)} filed outside the generator, kept as they are")
            for fname, table, key, cols, geo in TABLES:
                n = _load(cur, sb / f"{fname}.jsonl")
                if table == "crimes":
                    _guard_foreign(cur, foreign)
                _upsert(cur, table, key, cols, geo)
                print(f"{table}: {n} rows upserted")
                if table == "crimes":
                    _retire_stale_crimes(cur, retire, list(foreign))
            # section_map has a nullable natural key, so refresh it whole (nothing references it).
            n = _load(cur, sb / "section_map.jsonl")
            cur.execute("delete from public.section_map")
            cur.execute("insert into public.section_map (ipc_code, bns_code, title, category_group, source, verified) "
                        "select (r).ipc_code, (r).bns_code, (r).title, (r).category_group, (r).source, (r).verified "
                        "from (select jsonb_populate_record(null::public.section_map, doc) r from _stage) s")
            print(f"section_map: {n} rows")
            # crime_vehicles (identity key): insert only for crimes that have none yet, so existing
            # rows and their ids are never touched by a re-seed.
            n = _load(cur, sb / "crime_vehicles.jsonl")
            if retire:
                cur.execute("delete from public.crime_vehicles v using (select distinct doc->>'crime_id' cid "
                            "from _stage) s where v.crime_id = s.cid")
            cur.execute("delete from _stage s where exists (select 1 from public.crime_vehicles v "
                        "where v.crime_id = s.doc->>'crime_id')")
            cur.execute("insert into public.crime_vehicles (crime_id, role, vehicle_type, plate_pattern, make_model, "
                        "colour, synthetic) select (r).crime_id, (r).role, (r).vehicle_type, (r).plate_pattern, "
                        "(r).make_model, (r).colour, (r).synthetic "
                        "from (select jsonb_populate_record(null::public.crime_vehicles, doc) r from _stage) s")
            print(f"crime_vehicles: {cur.rowcount} inserted of {n} generated")
            # person_links: composite key, insert missing only.
            if (sb / "person_links.jsonl").is_file():
                n = _load(cur, sb / "person_links.jsonl")
                cur.execute("insert into public.person_links (person_id, crime_id, role, synthetic) "
                            "select (r).person_id, (r).crime_id, (r).role, (r).synthetic "
                            "from (select jsonb_populate_record(null::public.person_links, doc) r from _stage) s "
                            "on conflict do nothing")
                print(f"person_links: {n} rows")
            # Pulse Map projection cache (D-019): refreshed whole, never an agent source.
            for table in MAP_TABLES:
                f = sb / f"{table}.jsonl"
                if not f.is_file():
                    continue
                n = _load(cur, f)
                cur.execute(f"delete from public.{table}")
                cur.execute(f"insert into public.{table} select (jsonb_populate_record(null::public.{table}, doc)).* "
                            "from _stage")
                print(f"{table}: {n} rows")
            cur.execute("select pg_size_pretty(pg_database_size(current_database())), "
                        "pg_database_size(current_database())")
            pretty, size = cur.fetchone()
            print(f"database size: {pretty}")
            if size > 400 * 1024 * 1024:
                raise RuntimeError(f"database would be {pretty} (> 400 MB cap for the free tier); rolling back")
            cur.execute("select count(*) from public.crimes where synthetic")
            print(f"crimes in db (synthetic): {cur.fetchone()[0]}")
            if dry_run:
                raise _DryRun()


MAP_TABLES = ["map_cctv_cameras", "map_anpr_cameras", "map_anpr_reads", "map_call_cells", "map_release_density"]


class _DryRun(Exception):
    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--dry-run", action="store_true", help="run everything, then roll back")
    ap.add_argument("--retire", action="store_true",
                    help="allow deleting seeded crimes that are no longer generated (default: refuse)")
    a = ap.parse_args()
    if not os.environ.get("NEXUS_DB_PASSWORD"):
        sys.exit("NEXUS_DB_PASSWORD is not set (read it from the password file for this command only)")
    try:
        seed(Path(a.src), a.dry_run, a.retire)
    except _DryRun:
        print("dry run: rolled back")


if __name__ == "__main__":
    main()
