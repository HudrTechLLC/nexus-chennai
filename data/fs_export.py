"""Build the `nexus_fs` file-store tables from the generator output and the two committed fixtures (WS1-19).

    python -m data.fs_export --from data/generated            # writes data/generated/fs/<table>/part-0.parquet

Each table has the name, columns and Spark types of the sb object it replaces (DESCRIBE sb.<t> on our
Zetaris, 26 Oct), so the named queries' Lightning SQL runs unchanged on either source
(adapters/zetaris_sources.py):

- timestamps are real UTC instants (Parquet TIMESTAMP, adjusted to UTC);
- jsonb columns are strings in Postgres's jsonb text form (keys ordered by length then bytes, ", " and ": ");
- case_bundle_v is precomputed here with the text sb.case_bundle_v's json_agg / json_build_object produce
  (" : " inside objects, ", " between elements, timestamps as city-local ISO with offset), so nothing has to
  port that Postgres view to Spark;
- tips_v carries only the tips_v columns (no tip text, no passphrase hash), with Tip Guard's recorded
  verdicts from data/fixtures/tip_verdicts.parquet;
- crime_features_v comes from data/fixtures/crime_features_v.parquet (Nightshift output);
- link_alerts and forensics are empty tables with the schema (runtime data / none generated).

Columns no named query reads and the generator does not make (crimes.geom, created_at, updated_at) are NULL.
Every row is synthetic (rule R9). Nothing here is committed: it is rebuilt from the generator.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures"

# (column, DuckDB type) in sb column order. TIMESTAMPTZ -> Parquet TIMESTAMP(isAdjustedToUTC) -> Spark timestamp.
SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "crimes": [("crime_id", "VARCHAR"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"), ("station_id", "VARCHAR"),
               ("fir_no", "VARCHAR"), ("category", "VARCHAR"), ("sub_type", "VARCHAR"), ("sections", "VARCHAR"),
               ("occurred_from", "TIMESTAMPTZ"), ("occurred_to", "TIMESTAMPTZ"), ("reported_at", "TIMESTAMPTZ"),
               ("lat", "DOUBLE"), ("lon", "DOUBLE"), ("geom", "VARCHAR"), ("address", "VARCHAR"), ("ward_no", "INTEGER"),
               ("h3_r9", "VARCHAR"), ("h3_r8", "VARCHAR"), ("geohash7", "VARCHAR"), ("week", "VARCHAR"),
               ("severity", "INTEGER"), ("property", "VARCHAR"), ("weapon", "VARCHAR"),
               ("offenders_described", "VARCHAR"), ("victims", "VARCHAR"), ("status", "VARCHAR"),
               ("narrative", "VARCHAR"), ("synthetic", "BOOLEAN"), ("created_at", "TIMESTAMPTZ"),
               ("updated_at", "TIMESTAMPTZ")],
    "statements": [("statement_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("witness_ref", "VARCHAR"), ("mode", "VARCHAR"),
                   ("text", "VARCHAR"), ("audio_path", "VARCHAR"), ("transcript_model", "VARCHAR"),
                   ("recorded_at", "TIMESTAMPTZ"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"),
                   ("synthetic", "BOOLEAN")],
    "crime_vehicles": [("id", "BIGINT"), ("crime_id", "VARCHAR"), ("role", "VARCHAR"), ("vehicle_type", "VARCHAR"),
                       ("plate_pattern", "VARCHAR"), ("make_model", "VARCHAR"), ("colour", "VARCHAR"),
                       ("synthetic", "BOOLEAN")],
    "evidence_media": [("evidence_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("kind", "VARCHAR"),
                       ("storage_path", "VARCHAR"), ("sha256", "VARCHAR"), ("captured_at", "TIMESTAMPTZ"),
                       ("camera_id", "VARCHAR"), ("uploaded_by", "VARCHAR"), ("vision", "VARCHAR"),
                       ("custody", "VARCHAR"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"),
                       ("synthetic", "BOOLEAN"), ("created_at", "TIMESTAMPTZ")],
    "forensics": [("forensic_id", "VARCHAR"), ("crime_id", "VARCHAR"), ("kind", "VARCHAR"), ("match_code", "VARCHAR"),
                  ("reported_at", "TIMESTAMPTZ"), ("source", "VARCHAR"), ("source_row_id", "VARCHAR"),
                  ("synthetic", "BOOLEAN")],
    "crime_features_v": [("crime_id", "VARCHAR"), ("extractor_version", "VARCHAR"), ("mo", "VARCHAR"),
                         ("visual_tags", "VARCHAR"), ("entities", "VARCHAR"), ("model", "VARCHAR"),
                         ("receipt_id", "VARCHAR"), ("confidence", "FLOAT"), ("reviewed_by_officer", "BOOLEAN"),
                         ("synthetic", "BOOLEAN")],
    "tips_v": [("tip_id", "VARCHAR"), ("public_incident_id", "VARCHAR"), ("channel", "VARCHAR"), ("category", "VARCHAR"),
               ("guard", "VARCHAR"), ("approx_cell", "VARCHAR"), ("received_week", "VARCHAR"), ("status", "VARCHAR"),
               ("source", "VARCHAR"), ("source_row_id", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "section_map": [("id", "BIGINT"), ("ipc_code", "VARCHAR"), ("bns_code", "VARCHAR"), ("title", "VARCHAR"),
                    ("category_group", "VARCHAR"), ("source", "VARCHAR"), ("verified", "BOOLEAN")],
    "stations": [("station_id", "VARCHAR"), ("name", "VARCHAR"), ("type", "VARCHAR"), ("zone", "VARCHAR"),
                 ("district", "VARCHAR"), ("region", "VARCHAR"), ("synthetic", "BOOLEAN")],
    "link_alerts": [("alert_id", "VARCHAR"), ("kind", "VARCHAR"), ("crimes", "VARCHAR"), ("stations", "VARCHAR"),
                    ("score", "FLOAT"), ("band", "VARCHAR"), ("memory_applied", "VARCHAR"), ("skeptic", "VARCHAR"),
                    ("rationale", "VARCHAR"), ("recommended_action", "VARCHAR"), ("status", "VARCHAR"),
                    ("run_id", "VARCHAR"), ("created_at", "TIMESTAMPTZ"), ("updated_at", "TIMESTAMPTZ"),
                    ("synthetic", "BOOLEAN"), ("coverage", "FLOAT")],
}
JSONB = {"crimes": ("sections", "property", "offenders_described", "victims"), "evidence_media": ("vision", "custody")}
CASE_SCALARS = ("crime_id", "source", "source_row_id", "station_id", "fir_no", "category", "sub_type", "sections",
                "occurred_from", "occurred_to", "reported_at", "lat", "lon", "address", "ward_no", "h3_r9", "h3_r8",
                "geohash7", "week", "severity", "property", "weapon", "offenders_described", "victims", "status",
                "narrative", "synthetic")
SCHEMAS["case_bundle_v"] = (
    [(c, dict(SCHEMAS["crimes"])[c]) for c in CASE_SCALARS[:8]]
    + [(c, "VARCHAR") for c in ("occurred_from", "occurred_to", "reported_at")]  # city-local ISO text, as in 30_case.sql
    + [(c, dict(SCHEMAS["crimes"])[c]) for c in CASE_SCALARS[11:]]
    + [(c, "VARCHAR") for c in ("vehicles", "statements", "evidence", "forensics", "features")]
)


# ----------------------------------------------------------------------------- Postgres text forms

def _key(k: str) -> tuple[int, bytes]:
    b = k.encode("utf-8")
    return len(b), b


def jsonb_text(v: Any) -> str:
    """Postgres jsonb::text: keys ordered by length then bytes, ', ' and ': ' separators."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)}: {jsonb_text(v[k])}" for k in sorted(v, key=_key)) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(jsonb_text(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def json_object_text(pairs: list[tuple[str, str]]) -> str:
    """json_build_object(...)::text: keys in call order, ' : ' between key and value. Values are pre-rendered."""
    return "{" + ", ".join(f"{json.dumps(k, ensure_ascii=False)} : {v}" for k, v in pairs) + "}"


def _scalar(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def local_iso(ts: str | None, tz: ZoneInfo) -> str | None:
    """The 30_case.sql timestamp text: city-local ISO, fractional seconds only when non-zero, then the offset."""
    if ts is None:
        return None
    d = datetime.fromisoformat(ts).astimezone(tz)
    frac = f".{d.microsecond:06d}".rstrip("0") if d.microsecond else ""
    off = d.strftime("%z")
    return d.strftime("%Y-%m-%dT%H:%M:%S") + frac + f"{off[:3]}:{off[3:]}"


def _nulls_last(*vals: Any) -> tuple:
    """Postgres ORDER BY ascending puts NULLs last."""
    return tuple((v is None, v if v is not None else "") for v in vals)


# ----------------------------------------------------------------------------- build

def _jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.open(encoding="utf-8")] if path.is_file() else []


def build(src: Path, out: Path, fixtures: Path = FIXTURES, city: str = "chennai") -> dict[str, int]:
    tz = ZoneInfo(yaml.safe_load((ROOT / "cities" / city / "city.yaml").read_text(encoding="utf-8"))["timezone"])
    sb = src / "supabase"
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    for f in ("crime_features_v.parquet", "tip_verdicts.parquet"):
        if not (fixtures / f).is_file():
            raise SystemExit(f"missing fixture {fixtures / f}: export it with python -m data.fixtures.export")
    feats = con.execute(f"SELECT * FROM '{(fixtures / 'crime_features_v.parquet').as_posix()}'").fetchall()
    fcols = [d[0] for d in con.description]
    verdicts = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT tip_id, guard, status FROM '{(fixtures / 'tip_verdicts.parquet').as_posix()}'").fetchall()}

    crimes = _jl(sb / "crimes.jsonl")
    ids = {c["crime_id"] for c in crimes}
    rows: dict[str, list[dict[str, Any]]] = {t: [] for t in SCHEMAS}
    for c in crimes:
        rows["crimes"].append({**c, **{k: jsonb_text(c[k]) if c.get(k) is not None else None for k in JSONB["crimes"]}})
    rows["statements"] = _jl(sb / "statements.jsonl")
    rows["crime_vehicles"] = [{"id": i, **v} for i, v in enumerate(_jl(sb / "crime_vehicles.jsonl"), 1)]
    rows["evidence_media"] = [{**e, **{k: jsonb_text(e[k]) if e.get(k) is not None else None for k in JSONB["evidence_media"]}}
                              for e in _jl(sb / "evidence_media.jsonl")]
    rows["section_map"] = [{"id": i, **s} for i, s in enumerate(_jl(sb / "section_map.jsonl"), 1)]
    rows["stations"] = _jl(sb / "stations.jsonl")
    rows["crime_features_v"] = [dict(zip(fcols, f)) for f in feats if f[0] in ids]
    for t in _jl(sb / "tips.jsonl"):
        guard, status = verdicts.get(t["tip_id"], (None, t["status"]))
        rows["tips_v"].append({**t, "guard": guard, "status": status})
    rows["case_bundle_v"] = _case_bundles(rows, tz)

    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table, cols in SCHEMAS.items():
        (out / table).mkdir(exist_ok=True)
        _write(con, rows[table], cols, out / table / "part-0.parquet")
        counts[table] = len(rows[table])
    (out / "MANIFEST.json").write_text(json.dumps({"tables": counts, "synthetic": True}, indent=1) + "\n", encoding="utf-8")
    return counts


def _write(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]], cols: list[tuple[str, str]], path: Path) -> None:
    """Rows -> one Parquet file with exactly these column types. Rows go through a temporary NDJSON file read
    as text and cast once in SQL (row-by-row inserts take minutes for 20k rows)."""
    tmp = path.with_suffix(".ndjson")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps({c: (None if r.get(c) is None else str(r[c]) if not isinstance(r[c], bool)
                                     else ("true" if r[c] else "false")) for c, _ in cols}, ensure_ascii=False) + "\n")
    casts = ", ".join(f"CAST({c} AS {ty}) AS {c}" for c, ty in cols)
    if rows:
        spec = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c, _ in cols) + "}"
        src = f"read_json('{tmp.as_posix()}', format='newline_delimited', columns={spec})"
    else:
        src = "(SELECT " + ", ".join(f"CAST(NULL AS VARCHAR) AS {c}" for c, _ in cols) + " WHERE false)"
    con.execute(f"COPY (SELECT {casts} FROM {src} ORDER BY 1) TO '{path.as_posix()}' (FORMAT PARQUET)")
    tmp.unlink()


def _case_bundles(rows: dict[str, list[dict[str, Any]]], tz: ZoneInfo) -> list[dict[str, Any]]:
    def by_crime(table: str) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows[table]:
            out.setdefault(r["crime_id"], []).append(r)
        return out

    veh, st, ev, fo = by_crime("crime_vehicles"), by_crime("statements"), by_crime("evidence_media"), by_crime("forensics")
    latest: dict[str, dict[str, Any]] = {}
    for f in rows["crime_features_v"]:
        if f["crime_id"] not in latest or f["extractor_version"] > latest[f["crime_id"]]["extractor_version"]:
            latest[f["crime_id"]] = f

    def agg(items: list[str]) -> str:
        return "[" + ", ".join(items) + "]" if items else "[]"

    out = []
    for c in rows["crimes"]:
        cid = c["crime_id"]
        b = {k: c.get(k) for k in CASE_SCALARS}
        for k in ("occurred_from", "occurred_to", "reported_at"):
            b[k] = local_iso(c.get(k), tz)
        b["vehicles"] = agg([json_object_text([("role", _scalar(v["role"])), ("type", _scalar(v["vehicle_type"])),
                                               ("plate", _scalar(v["plate_pattern"])), ("make_model", _scalar(v["make_model"])),
                                               ("colour", _scalar(v["colour"]))])
                             for v in sorted(veh.get(cid, []), key=lambda v: _nulls_last(v["role"], v["plate_pattern"]))])
        b["statements"] = agg([json_object_text([("statement_id", _scalar(s["statement_id"])),
                                                 ("witness_ref", _scalar(s["witness_ref"])), ("mode", _scalar(s["mode"])),
                                                 ("text", _scalar(s["text"])),
                                                 ("recorded_at", _scalar(local_iso(s.get("recorded_at"), tz)))])
                               for s in sorted(st.get(cid, []), key=lambda s: s["statement_id"])])
        b["evidence"] = agg([json_object_text([("evidence_id", _scalar(e["evidence_id"])), ("kind", _scalar(e["kind"])),
                                               ("storage_path", _scalar(e["storage_path"])),
                                               ("captured_at", _scalar(local_iso(e.get("captured_at"), tz))),
                                               ("camera_id", _scalar(e["camera_id"])),
                                               ("vision", e["vision"] if e.get("vision") is not None else "null")])
                             for e in sorted(ev.get(cid, []), key=lambda e: e["evidence_id"])])
        b["forensics"] = agg([json_object_text([("forensic_id", _scalar(f["forensic_id"])), ("kind", _scalar(f["kind"])),
                                                ("match_code", _scalar(f["match_code"]))])
                              for f in sorted(fo.get(cid, []), key=lambda f: f["forensic_id"])])
        b["features"] = latest[cid]["bundle_json"] if cid in latest and "bundle_json" in latest[cid] else None
        out.append(b)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the nexus_fs file-store tables (WS1-19)")
    ap.add_argument("--from", dest="src", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--out", default=None, help="default: <from>/fs")
    ap.add_argument("--fixtures", default=str(FIXTURES), help="model-output fixtures (default data/fixtures)")
    a = ap.parse_args()
    src = Path(a.src)
    print(json.dumps(build(src, Path(a.out) if a.out else src / "fs", Path(a.fixtures))))


if __name__ == "__main__":
    main()
