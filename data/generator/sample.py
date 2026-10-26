"""Sample bundle for SAMPLE_MODE (WS1-11, spec P1): a closed subset of the generated city, as
parquet with the Supabase column types, plus the views the DuckDB twins query.

    NEXUS_DB_PASSWORD="$(tr -d '\\r\\n' < <password file>)" \\
      python -m data.generator.sample --from data/generated --out data/sample

What is in it
- The judge cases' series (Red Pulsar, Grille Cutters, Night Cab), their decoys, and every crime
  q_candidates would return for any of them (same category, <= DAYS UTC days, <= RING km), so the
  judge path sees the same candidates in sample mode as live.
- Duplicate pairs and DQ defects touching the subset, plus a few more, so q_dq_flags has work.
- The 40 public tips; live crime_features for the subset (with model + receipt), read from the DB.
- ref/ (place aliases, calendar, POIs), _truth/ restricted to the subset, views.sql.

It writes only its own paths; model_fixtures/, news/, social/ and crime_features.jsonl belong to
other lanes and are left alone. Rebuilding from the same generated data gives the same files,
except sb/crime_features.parquet, which follows the live extractor.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
JUDGE_IDS = ["CHN-AD-2026-001182", "CHN-KU-2025-000078", "CHN-GU-2025-000945"]
DAYS, RING_KM = 45, 10.0  # widest Planner window (ring 2 = 10 km), so every ring matches live
EXTRA_DUPLICATES, EXTRA_DQ_PER_RULE = 3, 2

# Supabase column types (public schema), minus geometry and audit columns. DuckDB types.
SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "crimes": [("crime_id", "VARCHAR"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"),
               ("station_id", "VARCHAR"), ("fir_no", "VARCHAR"), ("category", "VARCHAR"), ("sub_type", "VARCHAR"),
               ("sections", "VARCHAR"), ("occurred_from", "TIMESTAMPTZ"), ("occurred_to", "TIMESTAMPTZ"),
               ("reported_at", "TIMESTAMPTZ"), ("lat", "DOUBLE"), ("lon", "DOUBLE"), ("address", "VARCHAR"),
               ("ward_no", "INTEGER"), ("h3_r9", "VARCHAR"), ("h3_r8", "VARCHAR"), ("geohash7", "VARCHAR"),
               ("week", "VARCHAR"), ("severity", "SMALLINT"), ("property", "VARCHAR"), ("weapon", "VARCHAR"),
               ("offenders_described", "VARCHAR"), ("victims", "VARCHAR"), ("status", "VARCHAR"),
               ("narrative", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "crime_vehicles": [("crime_id", "VARCHAR"), ("role", "VARCHAR"), ("vehicle_type", "VARCHAR"),
                       ("plate_pattern", "VARCHAR"), ("make_model", "VARCHAR"), ("colour", "VARCHAR"),
                       ("synthetic", "BOOLEAN")],
    "statements": [("statement_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("witness_ref", "VARCHAR"),
                   ("mode", "VARCHAR"), ("text", "VARCHAR"), ("audio_path", "VARCHAR"),
                   ("transcript_model", "VARCHAR"), ("recorded_at", "TIMESTAMPTZ"), ("source", "VARCHAR"),
                   ("source_row_id", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "stations": [("station_id", "VARCHAR"), ("name", "VARCHAR"), ("type", "VARCHAR"), ("zone", "VARCHAR"),
                 ("district", "VARCHAR"), ("region", "VARCHAR"), ("lat", "DOUBLE"), ("lon", "DOUBLE"),
                 ("synthetic", "BOOLEAN")],
    "tips": [("tip_id", "VARCHAR"), ("public_incident_id", "VARCHAR"), ("channel", "VARCHAR"),
             ("category", "VARCHAR"), ("text", "VARCHAR"), ("follow_up_enabled", "BOOLEAN"),
             ("tip_code_hash", "VARCHAR"), ("guard", "VARCHAR"), ("approx_cell", "VARCHAR"),
             ("received_week", "VARCHAR"), ("status", "VARCHAR"), ("source", "VARCHAR"),
             ("source_row_id", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "evidence_media": [("evidence_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("kind", "VARCHAR"),
                       ("storage_path", "VARCHAR"), ("sha256", "VARCHAR"), ("captured_at", "TIMESTAMPTZ"),
                       ("camera_id", "VARCHAR"), ("uploaded_by", "VARCHAR"), ("vision", "VARCHAR"),
                       ("custody", "VARCHAR"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"),
                       ("synthetic", "BOOLEAN")],
    "forensics": [("forensic_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("kind", "VARCHAR"),
                  ("match_code", "VARCHAR"), ("reported_at", "TIMESTAMPTZ"), ("source", "VARCHAR"),
                  ("source_row_id", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "crime_features": [("crime_id", "VARCHAR"), ("extractor_version", "VARCHAR"), ("mo", "VARCHAR"),
                       ("visual_tags", "VARCHAR[]"), ("entities", "VARCHAR"), ("model", "VARCHAR"),
                       ("receipt_id", "VARCHAR"), ("confidence", "FLOAT"), ("reviewed_by", "VARCHAR"),
                       ("reviewed_at", "TIMESTAMPTZ"), ("synthetic", "BOOLEAN")],
    "crime_feature_reviews": [("review_id", "BIGINT"), ("crime_id", "VARCHAR"), ("corrections", "VARCHAR"),
                              ("note", "VARCHAR"), ("reviewed_by", "VARCHAR"), ("reviewed_at", "TIMESTAMPTZ"),
                              ("synthetic", "BOOLEAN")],
}
JSON_COLS = {"sections", "property", "offenders_described", "victims", "guard", "vision", "custody", "mo",
             "entities", "corrections"}

# v_crime_unified: the columns its consumers read (dq_rules, q_hex_counts, Linker), D3.1 flattened
# plus sections_raw (legacy rows only). zetaris/10_views.sql defines the same list.
UNIFIED_COLUMNS = [c for c, _ in SCHEMAS["crimes"] if c != "synthetic"] + ["sections_raw", "synthetic"]

VIEWS_SQL = """-- data/sample/views.sql: DuckDB views over the sample bundle, the names the twins query.
-- GENERATED by `python -m data.generator.sample`. Paths resolve against file_search_path = data/sample.
CREATE OR REPLACE VIEW v_crime_unified AS
SELECT {cols}, CAST(NULL AS VARCHAR) AS sections_raw, synthetic
FROM 'sb/crimes.parquet';
"""


def _jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _utc_day(ts: str):
    return datetime.fromisoformat(ts).astimezone(timezone.utc).date()


def _km(a: dict, b: dict) -> float:
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def select(crimes: dict[str, dict], truth: Path) -> tuple[set[str], dict]:
    """The closed subset: judge series + decoys + their q_candidates neighbours + DQ/duplicate rows."""
    series = json.loads((truth / "series.json").read_text(encoding="utf-8"))
    decoys = json.loads((truth / "decoys.json").read_text(encoding="utf-8"))
    dups = json.loads((truth / "duplicates.json").read_text(encoding="utf-8"))
    dq = json.loads((truth / "dq.json").read_text(encoding="utf-8"))
    judge_series = [s for s in series if set(s["crime_ids"]) & set(JUDGE_IDS)]
    sids = {s["series_id"] for s in judge_series}
    core = set(JUDGE_IDS)
    for s in judge_series:
        core |= set(s["crime_ids"])
    for d in decoys:
        if d["shadows_series_id"] in sids:
            core |= set(d["crime_ids"])
    by_cat: dict[str, list[dict]] = {}
    for c in crimes.values():
        by_cat.setdefault(c["category"], []).append(c)
    keep = set(core)
    for cid in sorted(core):
        a = crimes[cid]
        for b in by_cat[a["category"]]:
            if abs((_utc_day(a["occurred_from"]) - _utc_day(b["occurred_from"])).days) <= DAYS and _km(a, b) <= RING_KM:
                keep.add(b["crime_id"])
    touching = [p for p in dups if set(p["crime_ids"]) & keep]
    others = [p for p in dups if p not in touching][:EXTRA_DUPLICATES]
    for p in touching + others:
        keep |= set(p["crime_ids"])
    dq_rows = [r for r in dq if r.get("source") == "sb.crimes" and r["row_id"] in crimes]
    dq_keep = [r for r in dq_rows if r["row_id"] in keep]
    for rule in sorted({r["rule"] for r in dq_rows}):  # a few of every planted rule, so each DQ check has work
        dq_keep += [r for r in dq_rows if r["rule"] == rule and r["row_id"] not in keep][:EXTRA_DQ_PER_RULE]
    for r in dq_keep:
        keep.add(r["row_id"])
    return keep, {"judge_series": sorted(sids), "core": len(core), "duplicates": len(touching + others),
                  "dq": len(dq_keep)}


def _value(col: str, v):
    if col in JSON_COLS:
        return None if v is None else json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return v


def write_table(con, out: Path, table: str, rows: list[dict], order: list[str]) -> int:
    cols = SCHEMAS[table]
    con.execute(f"CREATE OR REPLACE TEMP TABLE t ({', '.join(f'{c} {t}' for c, t in cols)})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})",
                        [[_value(c, r.get(c)) for c, _ in cols] for r in rows])
    path = out / "sb" / f"{table}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM t ORDER BY {', '.join(order)}) TO '{path.as_posix()}' (FORMAT PARQUET)")
    return len(rows)


def live_features(ids: list[str]) -> list[dict]:
    """crime_features rows for the subset, from nexus-qa (model + receipt ids are real)."""
    if not os.environ.get("NEXUS_DB_PASSWORD"):
        print("NEXUS_DB_PASSWORD not set: sb/crime_features.parquet will be empty", file=sys.stderr)
        return []
    sys.path.insert(0, str(ROOT / "scripts"))
    from db_migrate import connect

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("select crime_id, extractor_version, mo, visual_tags, entities, model, receipt_id, confidence, "
                    "reviewed_by::text, reviewed_at, synthetic from public.crime_features where crime_id = any(%s)",
                    (ids,))
        names = [d.name for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


ANPR_BACKGROUND = 3000  # unrelated reads kept so a trail query has noise to cut through


def write_anpr(con, src: Path, out: Path, subset: list[dict]) -> int:
    """ANPR reads for the bundle: every read within 1.5 km / 2 h of a bundle crime, every read of a planted
    plate (series vehicles, vehicle chains), and a fixed background sample. Same columns as live."""
    plates = set()
    truth = src / "_truth"
    for s in json.loads((truth / "series.json").read_text(encoding="utf-8")):
        v = (s.get("true_mo") or {}).get("vehicle") or {}
        if v.get("plate"):
            plates.add(v["plate"].replace(" ", "").upper())
    if (truth / "vehicle_chains.json").is_file():
        for c in json.loads((truth / "vehicle_chains.json").read_text(encoding="utf-8")):
            if c.get("plate"):
                plates.add(c["plate"].replace(" ", "").upper())
    con.execute("CREATE OR REPLACE TEMP TABLE scenes (lat DOUBLE, lon DOUBLE, t TIMESTAMPTZ)")
    con.executemany("INSERT INTO scenes VALUES (?, ?, CAST(? AS TIMESTAMPTZ))",
                    [[c["lat"], c["lon"], c["occurred_from"]] for c in subset if c.get("lat") is not None])
    glob = (src / "anpr" / "reads_*.parquet").as_posix()
    path = out / "anpr" / "reads.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    plate_list = ", ".join("'" + p.replace("'", "") + "'" for p in sorted(plates)) or "''"
    con.execute(f"""
        COPY (
          WITH r AS (SELECT read_id, camera_id, read_at, plate_text, plate_confidence, direction, lat, lon, h3_r9,
                            synthetic FROM read_parquet('{glob}')),
          near AS (SELECT DISTINCT r.read_id FROM r JOIN scenes s
                   ON abs(r.lat - s.lat) <= 0.014 AND abs(r.lon - s.lon) <= 0.014
                  AND abs(epoch(r.read_at) - epoch(s.t)) <= 7200),
          keep AS (SELECT read_id FROM near
                   UNION SELECT read_id FROM r WHERE plate_text IN ({plate_list})
                   UNION SELECT read_id FROM (SELECT read_id FROM r ORDER BY hash(read_id), read_id
                                              LIMIT {ANPR_BACKGROUND}))
          SELECT r.* FROM r JOIN keep USING (read_id) ORDER BY r.read_id
        ) TO '{path.as_posix()}' (FORMAT PARQUET)""")
    return con.execute(f"SELECT count(*) FROM '{path.as_posix()}'").fetchone()[0]


def live_tip_guard(tips: list[dict]) -> list[dict]:
    """The generated tips with the live Tip Guard's recorded verdict (guard, status) where it has
    screened them, so sample mode corroborates like live. Never the passphrase hash."""
    if not os.environ.get("NEXUS_DB_PASSWORD"):
        return tips
    sys.path.insert(0, str(ROOT / "scripts"))
    from db_migrate import connect

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("select tip_id, guard, status from public.tips where tip_id = any(%s)", ([t["tip_id"] for t in tips],))
        live = {tid: (g, st) for tid, g, st in cur.fetchall()}
    return [t | ({"guard": live[t["tip_id"]][0], "status": live[t["tip_id"]][1]} if t["tip_id"] in live else {})
            for t in tips]


def _csv_subset(src: Path, dst: Path, keep=None) -> int:
    rows = list(csv.DictReader(src.open(encoding="utf-8", newline="")))
    rows = [r for r in rows if keep is None or keep(r)]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else [], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue().encode("utf-8"))
    return len(rows)


def build(src: Path, out: Path) -> dict:
    sb = src / "supabase"
    crimes = {c["crime_id"]: c for c in _jl(sb / "crimes.jsonl")}
    keep, info = select(crimes, src / "_truth")
    ids = sorted(keep)
    con = duckdb.connect()
    con.execute("SET threads = 1")  # stable row groups, so a rebuild gives the same bytes
    con.execute("SET TimeZone = 'UTC'")
    counts = {
        "crimes": write_table(con, out, "crimes", [crimes[i] for i in ids], ["crime_id"]),
        "crime_vehicles": write_table(con, out, "crime_vehicles",
                                      [v for v in _jl(sb / "crime_vehicles.jsonl") if v["crime_id"] in keep],
                                      ["crime_id", "role", "plate_pattern", "make_model"]),
        "statements": write_table(con, out, "statements",
                                  [s for s in _jl(sb / "statements.jsonl") if s["crime_id"] in keep], ["statement_id"]),
        "tips": write_table(con, out, "tips", live_tip_guard(_jl(sb / "tips.jsonl"))
                            if (sb / "tips.jsonl").is_file() else [], ["tip_id"]),
        "evidence_media": write_table(con, out, "evidence_media", [], ["evidence_id"]),
        "forensics": write_table(con, out, "forensics", [], ["forensic_id"]),
        "crime_features": write_table(con, out, "crime_features", live_features(ids), ["crime_id"]),
        "crime_feature_reviews": write_table(con, out, "crime_feature_reviews", [], ["review_id"]),
    }
    stations = []
    for s in _jl(sb / "stations.jsonl"):
        lon, lat = (s.get("centroid") or {}).get("coordinates") or (None, None)
        stations.append({k: s.get(k) for k, _ in SCHEMAS["stations"]} | {"lat": lat, "lon": lon})
    counts["stations"] = write_table(con, out, "stations", stations, ["station_id"])

    counts["anpr_reads"] = write_anpr(con, src, out, [crimes[i] for i in ids])
    ref = out / "ref"
    counts["place_aliases"] = _csv_subset(src / "ref" / "place_aliases.csv", ref / "place_aliases.csv")
    counts["calendar"] = _csv_subset(src / "ref" / "calendar.csv", ref / "calendar.csv")
    counts["releases"] = _csv_subset(src / "ref" / "releases.csv", ref / "releases.csv")
    counts["history_sheets"] = _csv_subset(src / "ref" / "history_sheets.csv", ref / "history_sheets.csv")
    ref.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / "ref" / "osm_pois.parquet", ref / "osm_pois.parquet")

    truth = out / "_truth"
    truth.mkdir(parents=True, exist_ok=True)
    for name in ("series", "decoys", "duplicates"):
        rows = json.loads((src / "_truth" / f"{name}.json").read_text(encoding="utf-8"))
        rows = [r | {"crime_ids": [c for c in r["crime_ids"] if c in keep]} for r in rows]
        rows = [r for r in rows if r["crime_ids"]]
        (truth / f"{name}.json").write_bytes((json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode())
    dq = [r for r in json.loads((src / "_truth" / "dq.json").read_text(encoding="utf-8"))
          if r.get("source") == "sb.crimes" and r["row_id"] in keep]
    (truth / "dq.json").write_bytes((json.dumps(dq, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode())
    if (src / "_truth" / "tips.json").is_file():
        shutil.copyfile(src / "_truth" / "tips.json", truth / "tips.json")
    _csv_subset(src / "_truth" / "pairs.csv", truth / "pairs.csv", lambda r: r["crime_a"] in keep and r["crime_b"] in keep)

    cols = ", ".join(c for c in UNIFIED_COLUMNS if c not in ("sections_raw", "synthetic"))
    (out / "views.sql").write_bytes(VIEWS_SQL.format(cols=cols).encode())
    manifest = {"synthetic": True, "judge_ids": JUDGE_IDS, "window": {"days": DAYS, "ring_km": RING_KM},
                "seed": json.loads((src / "MANIFEST.json").read_text(encoding="utf-8"))["seed"],
                **info, "counts": counts}
    (out / "MANIFEST.json").write_bytes((json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode())
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--out", default=str(ROOT / "data" / "sample"))
    a = ap.parse_args()
    print(json.dumps(build(Path(a.src), Path(a.out)), indent=1))


if __name__ == "__main__":
    main()
