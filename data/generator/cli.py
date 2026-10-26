"""python -m data.generator --seed 42 [--months 24] [--out data/generated] [--scale 1.0]

Slice 1 (WS1-08): crimes, crime_vehicles, statements, with 30 planted series (including the
spec's hero pair), 25 decoy clusters and 15 duplicate FIRs; the reference rows the seed needs
(stations, wards, section_map); _truth/ and MANIFEST.json. Same seed -> identical output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path

from . import crimes as C
from . import plant
from .context import ROOT, Ctx, load

NS = uuid.UUID("6f1c2a52-6a71-4c51-9e57-2c7b1b0a0e42")  # fixed namespace for source_row_id


# ---------- ids ----------
def short_codes(ctx: Ctx) -> dict[str, str]:
    fixed = {str(k): v for k, v in (ctx.cfg.get("station_short_codes") or {}).items()}
    used = set(fixed.values())
    out = {}
    for s in sorted(ctx.stations, key=lambda s: s.code):
        if s.code in fixed:
            out[s.station_id] = fixed[s.code]
            continue
        letters = re.sub(r"[^A-Z]", "", s.locality.upper())
        cands = [letters[0] + c for c in letters[1:]] + [letters[0] + c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        code = next(c for c in cands if c not in used)
        used.add(code)
        out[s.station_id] = code
    return out


def number_firs(ctx: Ctx, drafts: list[dict]) -> None:
    """FIR numbers per station-year, rising through the year with gaps (non-focus FIRs);
    reserved numbers (the hero pair) are never handed to another crime."""
    per_year = ctx.cfg["fir_numbers_per_year"]
    r = ctx.rng("fir-numbers")
    reserved: dict[tuple[str, int], set[int]] = {}
    for d in drafts:
        if d.get("fixed_fir"):
            n, y = d["fixed_fir"].split("/")
            reserved.setdefault((d["station"].station_id, int(y)), set()).add(int(n))
    groups: dict[tuple[str, int], list[dict]] = {}
    for d in drafts:
        groups.setdefault((d["station"].station_id, d["reported_at"].year), []).append(d)
    for key in sorted(groups):
        prev, res = 0, reserved.get(key, set())
        for d in sorted(groups[key], key=lambda x: (x["reported_at"], x["_key"])):
            if d.get("fixed_fir"):
                d["fir_n"] = int(d["fixed_fir"].split("/")[0])
                continue
            doy = d["reported_at"].timetuple().tm_yday
            n = max(prev + 1, int(doy / 366 * per_year) + r.randint(0, 3))
            while n in res:
                n += 1
            d["fir_n"], prev = n, n
    seen = set()
    for d in drafts:
        k = (d["station"].station_id, d["reported_at"].year, d["fir_n"])
        assert k not in seen, f"duplicate FIR number {k}"
        seen.add(k)


# ---------- rows ----------
def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def crime_row(d: dict) -> dict:
    return {
        "crime_id": d["crime_id"], "source": "sb.crimes", "source_row_id": str(uuid.uuid5(NS, d["crime_id"])),
        "station_id": d["station"].station_id, "fir_no": d["fir_no"], "category": d["category"],
        "sub_type": d["sub_type"], "sections": d["sections"], "occurred_from": _iso(d["occurred_from"]),
        "occurred_to": _iso(d["occurred_to"]), "reported_at": _iso(d["reported_at"]), "lat": d["lat"],
        "lon": d["lon"], "address": d["address"], "ward_no": d["ward_no"], "h3_r9": d["h3_r9"],
        "h3_r8": d["h3_r8"], "geohash7": d["geohash7"], "week": d["week"], "severity": d["severity"],
        "property": d["property"], "weapon": d["weapon"], "offenders_described": d["offenders"],
        "victims": d["victims"], "status": d["status"], "narrative": d["narrative"], "synthetic": True,
    }


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(dumps(r) for r in rows) + "\n").encode("utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue().encode("utf-8"))


# ---------- main ----------
def generate(seed: int, out: Path, months: int | None = None, scale: float = 1.0, city: str = "chennai") -> dict:
    ctx = load(seed, city, months)
    keyc = itertools.count()

    def keyed(d: dict) -> dict:
        d["_key"] = next(keyc)
        return d

    # Planted first (fixed streams), then background to fill the total.
    named = plant.named_series(None, ctx)
    gen = plant.generated_series(ctx, ctx.series_cfg["counts"]["series"] - len(named), set())
    series = named + gen
    for spec, members in series:
        r = ctx.rng(f"finish:{spec['series_id']}")
        for m in members:
            keyed(C.finish(r, ctx, m))
    decoys = plant.decoys(ctx, series, ctx.series_cfg["counts"]["decoys"])
    for _, cluster in decoys:
        for d in cluster:
            keyed(d)

    planted = sum(len(m) for _, m in series) + sum(len(c) for _, c in decoys) + ctx.series_cfg["counts"]["duplicates"]
    n_bg = max(0, round((ctx.cfg["total_firs"] - planted) * scale))
    types = sorted(ctx.cfg["crime_types"])
    shares = [ctx.cfg["crime_types"][t]["share"] for t in types]
    rb = ctx.rng("background")
    bg = [keyed(C.background(rb, ctx, t)) for t in rb.choices(types, weights=shares, k=n_bg)]
    dups = plant.duplicates(ctx, bg, ctx.series_cfg["counts"]["duplicates"])
    for _, d in dups:
        keyed(d)

    drafts = [m for _, ms in series for m in ms] + [d for _, c in decoys for d in c] + bg + [d for _, d in dups]
    number_firs(ctx, drafts)
    sc = short_codes(ctx)
    for d in drafts:
        y = d["reported_at"].year
        d["fir_no"] = f"{d['fir_n']}/{y}"
        d["crime_id"] = d.get("fixed_id") or f"{ctx.cfg['id_prefix']}-{sc[d['station'].station_id]}-{y}-{d['fir_n']:06d}"
    ids = [d["crime_id"] for d in drafts]
    assert len(ids) == len(set(ids)), "duplicate crime ids"
    by_key = {d["_key"]: d for d in drafts}
    drafts.sort(key=lambda d: d["crime_id"])

    # ---- Supabase rows ----
    sb = out / "supabase"
    crimes = [crime_row(d) for d in drafts]
    vehicles, stmts = [], []
    for d in drafts:
        for v in d["vehicles"]:
            vehicles.append({"crime_id": d["crime_id"], "role": v["role"], "vehicle_type": v["type"],
                             "plate_pattern": re.sub(r"[^A-Z0-9?]", "", v["plate"].upper()) if v.get("plate") else None,
                             "plate_display": v.get("plate"), "make_model": v.get("make_model"),
                             "colour": v.get("colour"), "synthetic": True})
        for s in d["statements"]:
            stmts.append({"crime_id": d["crime_id"], **s, "recorded_at": _iso(s["recorded_at"]),
                          "audio_path": None, "transcript_model": None, "source": "sb.statements", "synthetic": True})
    for i, s in enumerate(stmts):
        s["statement_id"] = f"ST-{i + 1:06d}"
        s["source_row_id"] = s["statement_id"]
    write_jsonl(sb / "crimes.jsonl", crimes)
    write_jsonl(sb / "crime_vehicles.jsonl", vehicles)
    write_jsonl(sb / "statements.jsonl", stmts)
    write_jsonl(sb / "stations.jsonl", [
        {"station_id": s.station_id, "name": s.name, "type": "law_and_order", "zone": s.zone, "district": s.district,
         "region": s.region, "geom": s.feature["geometry"], "centroid": {"type": "Point", "coordinates": [s.lon, s.lat]},
         "synthetic": True} for s in ctx.stations])
    write_jsonl(sb / "wards.jsonl", [
        {"ward_no": f["properties"]["ward_no"], "name": f["properties"]["name"], "zone": f["properties"]["zone"],
         "geom": f["geometry"]} for f in sorted(ctx.ward_features, key=lambda f: f["properties"]["ward_no"])])
    write_jsonl(sb / "section_map.jsonl", [
        {"ipc_code": r["ipc_code"] or None, "bns_code": r["bns_code"] or None, "title": r["title"],
         "category_group": r["category_group"], "source": "bns_text", "verified": r["verified"] == "true"}
        for r in ctx.section_rows])

    # ---- ground truth ----
    truth = out / "_truth"
    write_json(truth / "series.json", [{
        "series_id": spec["series_id"], "name": spec["name"], "kind": "series", "category": members[0]["category"],
        "crime_type": spec["crime_type"], "crime_ids": sorted(m["crime_id"] for m in members),
        "stations": sorted({m["station"].station_id for m in members}),
        "true_mo": {"mo": members[0]["mo"] | {"time_band": None}, "offenders": members[0]["offenders"][0],
                    "vehicle": (spec.get("vehicle") or (spec.get("true_mo") or {}).get("vehicle")),
                    "signature": members[0].get("signature"), "weapon": members[0].get("weapon")},
    } for spec, members in series])
    pairs = []
    for spec, members in series:
        for a, b in itertools.combinations(sorted(m["crime_id"] for m in members), 2):
            pairs.append([a, b, "series", spec["series_id"]])
    for meta, cluster in decoys:
        members = next(ms for sp, ms in series if sp["series_id"] == meta["shadows_series_id"])
        for d in cluster:
            for m in members:
                if plant.blocks(d, m):
                    a, b = sorted([d["crime_id"], m["crime_id"]])
                    pairs.append([a, b, "decoy", meta["decoy_id"]])
    for i, (orig, dup) in enumerate(dups):
        a, b = sorted([orig["crime_id"], dup["crime_id"]])
        pairs.append([a, b, "duplicate", f"DUP-{i + 1:02d}"])
    pairs.sort()
    write_csv(truth / "pairs.csv", ["crime_a", "crime_b", "label", "group_id"], pairs)
    write_json(truth / "decoys.json", [{"decoy_id": m["decoy_id"], "shadows_series_id": m["shadows_series_id"],
                                        "crime_ids": sorted(d["crime_id"] for d in c)} for m, c in decoys])
    write_json(truth / "duplicates.json", [{"dup_id": f"DUP-{i + 1:02d}",
                                            "crime_ids": sorted([o["crime_id"], d["crime_id"]])}
                                           for i, (o, d) in enumerate(dups)])

    # ---- manifest (hash of logical content, so it is stable across platforms) ----
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "MANIFEST.json")
    manifest = {
        "seed": seed, "city": city, "end_date": ctx.end.isoformat(), "start_date": ctx.start.isoformat(),
        "scale": scale, "synthetic": True,
        "counts": {"crimes": len(crimes), "crime_vehicles": len(vehicles), "statements": len(stmts),
                   "stations": len(ctx.stations), "wards": len(ctx.ward_features), "series": len(series),
                   "series_crimes": sum(len(m) for _, m in series), "decoy_clusters": len(decoys),
                   "decoy_crimes": sum(len(c) for _, c in decoys), "duplicates": len(dups),
                   "pairs": {lab: sum(1 for p in pairs if p[2] == lab) for lab in ("series", "decoy", "duplicate")}},
        "sha256": {p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    write_json(out / "MANIFEST.json", manifest)
    _ = by_key, date
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--months", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "generated"))
    ap.add_argument("--scale", type=float, default=1.0, help="scale background volume (planted items stay whole)")
    ap.add_argument("--city", default="chennai")
    a = ap.parse_args()
    m = generate(a.seed, Path(a.out), a.months, a.scale, a.city)
    print(json.dumps(m["counts"], indent=1))
