"""Slice 2 wiring: plant chains/returns/DQ before FIR numbering; write the other sources after."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from . import plant2
from . import sources as S
from .context import ROOT, Ctx


def plant_more(ctx: Ctx, bg: list[dict], keyed) -> dict:
    chains = plant2.vehicle_chains(ctx, bg, 12)
    for c in chains:
        for u in c["uses"]:
            keyed(u)
    returns = plant2.offender_returns(ctx, 10)
    for ret in returns:
        for d in ret["returns"]:
            keyed(d)
    return {"chains": chains, "returns": returns, "dq": []}  # dq is planted after numbering (cli.generate)


# ---------- writers ----------
def _csv_text(header: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if r.get(h) is None else (r[h].isoformat(timespec="seconds") if isinstance(r[h], datetime)
                                                 else r[h]) for h in header])
    return buf.getvalue()


def write_csv(path: Path, header: list[str], rows: list[dict], hashes: dict, out: Path) -> None:
    text = _csv_text(header, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    hashes[path.relative_to(out).as_posix()] = hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_parquet(path: Path, header: list[str], types: dict[str, str], rows: list[dict], hashes: dict,
                  out: Path) -> None:
    """CSV -> DuckDB -> Parquet. The manifest hashes the CSV (logical content), not Parquet bytes."""
    text = _csv_text(header, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "rows.csv"
        tmp.write_bytes(text.encode("utf-8"))
        cols = "{" + ", ".join(f"'{h}': '{types.get(h, 'VARCHAR')}'" for h in header) + "}"
        con = duckdb.connect()
        con.execute("SET threads=1")
        con.execute("SET TimeZone='UTC'")
        con.execute(f"COPY (SELECT * FROM read_csv('{tmp.as_posix()}', header=true, columns={cols}, "
                    f"timestampformat='%Y-%m-%dT%H:%M:%S%z')) TO '{path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
        con.close()
    hashes[path.relative_to(out).as_posix()] = hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def enc(v):
        return v.isoformat(timespec="seconds") if isinstance(v, datetime) else v
    path.write_bytes(("\n".join(json.dumps({k: enc(v) for k, v in r.items()}, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")) for r in rows) + "\n").encode("utf-8"))


def _by_month(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(f"{r[key]:%Y_%m}", []).append(r)
    return out


# ---------- sources ----------
ANPR_COLS = ["read_id", "camera_id", "read_at", "plate_text", "plate_confidence", "direction", "lat", "lon", "h3_r9",
             "crime_id", "synthetic"]
ANPR_TYPES = {"read_at": "TIMESTAMPTZ", "plate_confidence": "DOUBLE", "lat": "DOUBLE", "lon": "DOUBLE",
              "synthetic": "BOOLEAN"}
CALL_COLS = ["call_id", "received_at", "caller", "category", "lat", "lon", "cell", "dispatched_unit", "outcome",
             "fir_ref", "crime_id", "synthetic"]
CALL_TYPES = {"received_at": "TIMESTAMPTZ", "lat": "DOUBLE", "lon": "DOUBLE", "synthetic": "BOOLEAN"}
ARC_COLS = ["case_ref", "station_name", "crime_head", "crime_subhead", "date_of_occurrence", "time_of_occurrence",
            "latitude", "longitude", "ipc_sections", "accused_ids", "mo_tags", "property_value", "disposal", "synthetic"]
ARC_TYPES = {"latitude": "DOUBLE", "longitude": "DOUBLE", "property_value": "BIGINT", "synthetic": "BOOLEAN"}
CCTNS_COLS = ["PS_CODE", "FIR_NUM", "FIR_DT", "OCC_DT_FROM", "OCC_DT_TO", "ACT_SEC", "MAJOR_HEAD", "MINOR_HEAD",
              "PLACE_OCC", "LAT", "LONG", "BRIEF_FACTS", "PROP_STOLEN_RS", "IO_NAME"]


def _series_plates(series) -> dict[str, str]:
    out = {}
    for spec, _ in series:
        v = spec.get("vehicle") or (spec.get("true_mo") or {}).get("vehicle")
        if v and v.get("plate"):
            out[spec["series_id"]] = v["plate"]
    return out


def write_sources(ctx: Ctx, out: Path, drafts: list[dict], series, more: dict, scale: float) -> dict:
    hashes: dict[str, str] = {}
    plates = _series_plates(series)
    cams = S.anpr_cameras(ctx, 140)

    sightings = []
    for spec, members in series:
        p = plates.get(spec["series_id"])
        if not p:
            continue
        for m in members:
            if m.get("hero"):
                continue
            sightings.append({"plate": p, "at": m["occurred_from"], "lat": m["lat"], "lon": m["lon"],
                              "crime_id": m["crime_id"], "minutes": (-60, 60)})
    hero = {d["crime_id"]: d for d in drafts if d.get("hero")}
    tz = ctx.tz
    if "CHN-AD-2026-001182" in hero:
        sightings.append({"plate": "TN 09 BX 4471", "camera_id": "ANPR-OMR-12", "at": datetime(2026, 10, 14, 19, 58, 41, tzinfo=tz),
                          "confidence": 0.81, "direction": "N", "crime_id": "CHN-AD-2026-001182"})
    if "CHN-VL-2026-000877" in hero:
        sightings.append({"plate": "TN 09 BX 4471", "camera_id": "ANPR-VLY-03", "at": datetime(2026, 10, 16, 19, 46, 12, tzinfo=tz),
                          "confidence": 0.77, "direction": "S", "crime_id": "CHN-VL-2026-000877"})
    for c in more["chains"]:
        t0 = c["theft"]["occurred_from"]
        last = max(u["occurred_from"] for u in c["uses"])
        for k in range(3):
            at = t0 + (last - t0) * (k + 1) / 4
            sightings.append({"plate": c["plate"], "at": at, "lat": c["uses"][0]["lat"], "lon": c["uses"][0]["lon"],
                              "crime_id": None, "minutes": (-30, 30)})
        for u in c["uses"]:
            sightings.append({"plate": c["plate"], "at": u["occurred_from"], "lat": u["lat"], "lon": u["lon"],
                              "crime_id": u["crime_id"], "minutes": (-40, 40)})
    planted = S.planted_reads(ctx, cams, sightings)
    register = S.vehicles_register(ctx, drafts, sorted(set(plates.values())), max(3000, round(25000 * scale)))
    reads = S.anpr_reads(ctx, cams, register, planted, max(len(planted) + 100, round(600000 * scale)))
    for month, rows in sorted(_by_month(reads, "read_at").items()):
        write_parquet(out / "anpr" / f"reads_{month}.parquet", ANPR_COLS, ANPR_TYPES, rows, hashes, out)
    write_csv(out / "ref" / "anpr_cameras.csv", ["camera_id", "lat", "lon", "h3_r9", "synthetic"], cams, hashes, out)
    write_csv(out / "ref" / "vehicles.csv", ["plate", "plate_compact", "vehicle_type", "make_model", "colour", "status",
                                             "owner_ref", "reg_year", "registered_ward", "synthetic"], register, hashes, out)

    cctv = S.cctv_cameras(ctx, max(300, round(2500 * scale)))
    write_csv(out / "ref" / "cctv_cameras.csv", ["camera_id", "owner_type", "owner_name", "lat", "lon", "heading_deg",
                                                 "fov_deg", "range_m", "retention_days", "contact_station", "last_updated",
                                                 "h3_r9", "synthetic"], cctv, hashes, out)

    calls = S.calls(ctx, drafts, max(100, round(120000 * scale)))
    for month, rows in sorted(_by_month(calls, "received_at").items()):
        write_parquet(out / "calls" / f"calls_{month}.parquet", CALL_COLS, CALL_TYPES, rows, hashes, out)

    reg = S.persons_and_registers(ctx, drafts, more["returns"], max(800, round(9000 * scale)),
                                  max(150, round(1800 * scale)), max(120, round(1200 * scale)))
    write_csv(out / "ref" / "releases.csv", ["release_id", "person_ref", "released_on", "release_type", "prior_mo_tags",
                                             "residence_ward", "station_of_residence", "synthetic"],
              reg["releases"], hashes, out)
    write_csv(out / "ref" / "history_sheets.csv", ["sheet_id", "person_ref", "station_id", "opened_on", "category",
                                                   "mo_tags", "residence_ward", "active", "synthetic"],
              reg["history_sheets"], hashes, out)
    write_jsonl(out / "supabase" / "persons.jsonl", reg["persons"])
    write_jsonl(out / "supabase" / "person_links.jsonl", reg["person_links"])

    leg = S.legacy(ctx, max(200, round(3000 * scale)), max(100, round(2500 * scale)), more["returns"])
    for ps, rows in sorted(leg["cctns"].items()):
        write_csv(out / "legacy" / f"cctns_{ps}.csv", CCTNS_COLS, rows, hashes, out)
    write_parquet(out / "legacy" / "archive.parquet", ARC_COLS, ARC_TYPES, leg["archive"], hashes, out)

    # place aliases: add station_id and ward_no (ward of the station's location) for joins
    al = ctx.pack / "place_aliases.csv"
    if al.is_file():
        rows = []
        for row in csv.DictReader(al.open(encoding="utf-8")):
            st = ctx.by_code.get(row["station_code"])
            rows.append({"alias": row["alias"], "canonical": row["canonical"], "station_code": row["station_code"],
                         "station_id": st.station_id if st else None,
                         "ward_no": ctx.ward_at(st.lat, st.lon) if st else None, "note": row["note"]})
        write_csv(out / "ref" / "place_aliases.csv", ["alias", "canonical", "station_code", "station_id", "ward_no",
                                                      "note"], rows, hashes, out)
    for name in ("calendar.csv",):
        src = ctx.pack / name
        if src.is_file():
            (out / "ref").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out / "ref" / name)
            hashes[f"ref/{name}"] = hashlib.sha256(src.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    shutil.copyfile(ROOT / "data" / "reference" / "osm_pois.parquet", out / "ref" / "osm_pois.parquet")

    # ---- Pulse Map projection cache (D-019): never an agent source ----
    write_jsonl(out / "supabase" / "map_cctv_cameras.jsonl", [
        {k: c[k] for k in ("camera_id", "owner_type", "lat", "lon", "heading_deg", "fov_deg", "range_m", "h3_r9",
                           "contact_station", "synthetic")} for c in cctv])
    write_jsonl(out / "supabase" / "map_anpr_cameras.jsonl", cams)
    write_jsonl(out / "supabase" / "map_anpr_reads.jsonl", [
        {k: x[k] for k in ("read_id", "camera_id", "read_at", "plate_text", "plate_confidence", "direction", "lat",
                           "lon", "crime_id", "synthetic")} for x in reads if x["crime_id"]])
    cells: dict[tuple, int] = {}
    for c in calls:
        hb = c["received_at"].replace(minute=0, second=0, microsecond=0)
        cells[(c["cell"], c["category"], hb)] = cells.get((c["cell"], c["category"], hb), 0) + 1
    write_jsonl(out / "supabase" / "map_call_cells.jsonl", [
        {"h3_r9": k[0], "category": k[1], "hour_bucket": k[2], "n": n, "synthetic": True} for k, n in sorted(cells.items())])
    dens: dict[int, list] = {}
    for rel in reg["releases"]:
        if rel["residence_ward"] is not None:
            dens.setdefault(rel["residence_ward"], []).append(rel["released_on"])
    from datetime import date as _d
    write_jsonl(out / "supabase" / "map_release_density.jsonl", [
        {"ward_no": w, "n": len(v), "last_release_week": "{}-W{:02d}".format(*_d.fromisoformat(max(v)).isocalendar()[:2]),
         "synthetic": True} for w, v in sorted(dens.items())])

    # ---- truth ----
    crime_by_key = {d["_key"]: d for d in drafts}
    dq = [{"rule": x["rule"], "source": "sb.crimes", "row_id": crime_by_key[x["crime_key"]]["crime_id"]}
          for x in more["dq"]] + leg["dq"]
    dq += [{"rule": "dq_stale_cameras", "source": "s3csv.cctv_cameras", "row_id": c["camera_id"]} for c in cctv
           if (ctx.end - _d.fromisoformat(c["last_updated"])).days > 180]
    truth = {
        "vehicle_chains": [{"chain_id": c["chain_id"], "theft_crime_id": c["theft"]["crime_id"],
                            "use_crime_ids": sorted(u["crime_id"] for u in c["uses"]), "plate": c["plate"]}
                           for c in more["chains"]],
        "offender_returns": [{"return_id": x["return_id"], "person_ref": x["person_ref"],
                              "release_id": f"REL-R{x['return_id'][3:]}", "released_on": x["released_on"].isoformat(),
                              "residence_ward": x["ward_no"], "mo_tags": x["mo_tags"],
                              "return_crime_ids": sorted(d["crime_id"] for d in x["returns"]),
                              "prior_case_refs": sorted(a["case_ref"] for a in leg["archive"]
                                                        if a["accused_ids"] == x["person_ref"])}
                             for x in more["returns"]],
        "dq": sorted(dq, key=lambda x: (x["rule"], x["row_id"])),
    }
    counts = {"anpr_reads": len(reads), "anpr_planted": len(planted), "anpr_cameras": len(cams),
              "vehicles": len(register), "cctv_cameras": len(cctv), "calls": len(calls),
              "persons": len(reg["persons"]), "person_links": len(reg["person_links"]),
              "releases": len(reg["releases"]), "history_sheets": len(reg["history_sheets"]),
              "cctns_rows": sum(len(v) for v in leg["cctns"].values()), "archive_rows": len(leg["archive"]),
              "vehicle_chains": len(more["chains"]), "offender_returns": len(more["returns"]), "dq_planted": len(dq)}
    _ = timedelta
    return {"hashes": hashes, "truth": truth, "counts": counts}
