"""The other D1 sources, laid out like the bucket (WS1-08 slice 2).

  ref/vehicles.csv          D1 #8   vehicles register (every plate seen in a crime is in it)
  ref/cctv_cameras.csv      D1 #10  CCTV registry (D3.10), some stale (dq_stale_cameras)
  ref/anpr_cameras.csv              ANPR camera registry (positions for v_vehicle_trail)
  anpr/reads_YYYY_MM.parquet D1 #9  ANPR reads (D3.9): background traffic + planted sightings
  calls/calls_YYYY_MM.parquet D1 #11 112 calls (D3.8): calls for most FIRs + unreported noise
  ref/releases.csv          D1 #12  prison releases / bail (D3.10)
  ref/history_sheets.csv    D1 #13  history sheets
  legacy/cctns_<ps>.csv     D1 #2   legacy CCTNS export (D3.3 columns, IPC, DD-MM-YYYY, upper case)
  legacy/archive.parquet    D1 #3   pre-window archive in another schema
  supabase/persons.jsonl, person_links.jsonl  D1 #7
Every row carries synthetic = true. Hash-stable: rows are generated in a fixed order from
named streams and sorted before writing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from data.geo import cells, km, offset

from . import crimes as C
from .context import Ctx

HERO_CAMS = {  # spec D3.9 / D3.11 / D3.4 examples
    "ANPR-OMR-12": (12.9921, 80.2510),
    "ANPR-VLY-03": (12.9845, 80.2235),
}
HERO_CCTV = {"camera_id": "CAM-LB-0192", "owner_type": "private_shop", "owner_name": "Sri Murugan Jewellers (synthetic)",
             "lat": 13.0011, "lon": 80.2567, "heading_deg": 210, "fov_deg": 90, "range_m": 40, "retention_days": 15}
CALL_NOISE = ["noise_complaint", "traffic_accident", "medical_emergency", "quarrel", "suspicious_person",
              "drunk_and_disorderly", "fire", "missing_child_found", "animal_menace", "power_line_down"]
MAJOR_HEAD = {"robbery": "ROBBERY", "theft": "THEFT", "house_break": "HOUSE BREAKING", "hurt": "HURT",
              "cheating": "CHEATING", "crimes_against_women": "CRIME AGAINST WOMEN", "homicide": "MURDER",
              "kidnapping": "KIDNAPPING"}


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _farthest(points: list[tuple[float, float]], k: int, start: int = 0) -> list[int]:
    """Deterministic farthest-point sampling: spreads cameras across the city."""
    chosen = [start]
    best = [km(*points[start], *p) for p in points]
    while len(chosen) < k:
        i = max(range(len(points)), key=lambda j: best[j])
        chosen.append(i)
        best = [min(best[j], km(*points[i], *points[j])) for j in range(len(points))]
    return chosen


# ---------- cameras ----------
def anpr_cameras(ctx: Ctx, n: int) -> list[dict]:
    pts = sorted({(p[0], p[1]) for t in ("bus_station", "metro_station", "railway_station", "fuel") for p in ctx.pois.get(t, [])})
    idx = _farthest(pts, n - len(HERO_CAMS))
    rows, seq = [], {}
    for cid, (lat, lon) in HERO_CAMS.items():
        rows.append({"camera_id": cid, "lat": lat, "lon": lon})
    for i in idx:
        lat, lon = pts[i]
        st = ctx.station_at(lat, lon) or min(ctx.stations, key=lambda s: km(lat, lon, s.lat, s.lon))
        tag = "".join(ch for ch in st.locality.upper() if ch.isalpha())[:3]
        seq[tag] = seq.get(tag, 0) + 1
        cid = f"ANPR-{tag}-{seq[tag]:02d}"
        while cid in HERO_CAMS:
            seq[tag] += 1
            cid = f"ANPR-{tag}-{seq[tag]:02d}"
        rows.append({"camera_id": cid, "lat": round(lat, 6), "lon": round(lon, 6)})
    for r in rows:
        r["h3_r9"] = cells(r["lat"], r["lon"])["h3_r9"]
        r["synthetic"] = True
    return sorted(rows, key=lambda r: r["camera_id"])


def cctv_cameras(ctx: Ctx, n: int) -> list[dict]:
    r = ctx.rng("cctv")
    shops = [p for t in ("jeweller", "supermarket", "mobile_shop", "bank", "atm", "hotel", "restaurant", "pharmacy")
             for p in ctx.pois.get(t, [])]
    junctions = ctx.pois.get("bus_stop", [])
    rows = [dict(HERO_CCTV)]
    for i in range(n - 1):
        kind = r.choices(["private_shop", "police", "community"], weights=[5, 3, 2])[0]
        lat, lon, name = r.choice(shops if kind == "private_shop" else junctions)
        lat, lon = offset(lat, lon, r.uniform(0.0, 0.05), r.uniform(0, 360))
        owner = f"{name} (synthetic)" if (kind == "private_shop" and name) else \
            {"police": "Greater Chennai Police", "community": "Residents' welfare association (synthetic)",
             "private_shop": "Shop (synthetic)"}[kind]
        rows.append({"camera_id": f"CAM-{i + 1:05d}", "owner_type": kind, "owner_name": owner,
                     "lat": round(lat, 6), "lon": round(lon, 6), "heading_deg": r.randrange(0, 360),
                     "fov_deg": r.choice([60, 90, 110]), "range_m": r.choice([20, 30, 40, 60]),
                     "retention_days": r.choice([7, 15, 30])})
    for row in rows:
        st = ctx.station_at(row["lat"], row["lon"]) or min(ctx.stations, key=lambda s: km(row["lat"], row["lon"], s.lat, s.lon))
        row["contact_station"] = st.station_id
        stale = r.random() < 0.05 and row["camera_id"] != HERO_CCTV["camera_id"]
        row["last_updated"] = (ctx.end - timedelta(days=r.randint(200, 600) if stale else r.randint(1, 150))).isoformat()
        row["h3_r9"] = cells(row["lat"], row["lon"])["h3_r9"]
        row["synthetic"] = True
    return sorted(rows, key=lambda r: r["camera_id"])


# ---------- vehicles register ----------
def vehicles_register(ctx: Ctx, drafts: list[dict], extra_plates: list[str], n: int) -> list[dict]:
    r = ctx.rng("vehicles")
    gcc = [w[0] for w in ctx.wards if w[0] != 0]
    known: dict[str, dict] = {}
    for d in drafts:
        for v in d["vehicles"]:
            if v.get("plate") and "?" not in v["plate"]:
                known.setdefault(v["plate"], {"vehicle_type": v["type"], "make_model": v["make_model"],
                                              "colour": v["colour"], "status": "reported_stolen"
                                              if v["role"] == "stolen" else "active"})
    for p in extra_plates:
        known.setdefault(p, {"vehicle_type": "motorcycle", "make_model": r.choice(C.MOTORCYCLES),
                             "colour": r.choice(C.COLOURS), "status": "active"})
    while len(known) < n:
        two = r.random() < 0.7
        known.setdefault(C.plate(r), {"vehicle_type": "motorcycle" if two else "car",
                                      "make_model": r.choice(C.MOTORCYCLES if two else C.CARS),
                                      "colour": r.choice(C.COLOURS), "status": "active"})
    rows = []
    for i, p in enumerate(sorted(known)):
        rows.append({"plate": p, "plate_compact": p.replace(" ", ""), **known[p], "owner_ref": f"OWN-{i + 1:06d}",
                     "reg_year": r.randint(2008, 2026), "registered_ward": r.choice(gcc), "synthetic": True})
    return rows


# ---------- ANPR reads ----------
def anpr_reads(ctx: Ctx, cams: list[dict], register: list[dict], planted: list[dict], n: int) -> list[dict]:
    """Background traffic plus planted sightings (planted rows come pre-built with crime_id)."""
    r = ctx.rng("anpr")
    plates = [v["plate_compact"] for v in register]
    regulars = plates[: max(50, len(plates) // 5)]  # commuters pass cameras often
    days = ctx.days()
    rows = []
    for _ in range(max(0, n - len(planted))):
        cam = r.choice(cams)
        p = r.choice(regulars) if r.random() < 0.6 else r.choice(plates)
        conf = round(r.uniform(0.55, 0.99), 2)
        if conf < 0.65:
            k = r.randrange(4, len(p))
            p = p[:k] + "?" + p[k + 1:]
        hour = C.pick_hour(r, [[6, 10, 3], [10, 17, 2], [17, 22, 3], [22, 24, 1], [0, 6, 0.3]])
        rows.append({"camera_id": cam["camera_id"], "read_at": ctx.local(r.choice(days), hour) + timedelta(seconds=r.randint(0, 59)),
                     "plate_text": p, "plate_confidence": conf, "direction": r.choice(["N", "S", "E", "W"]),
                     "lat": cam["lat"], "lon": cam["lon"], "h3_r9": cam["h3_r9"], "crime_id": None})
    rows.extend(planted)
    rows.sort(key=lambda x: (x["read_at"], x["camera_id"], x["plate_text"]))
    for i, row in enumerate(rows):
        row["read_id"] = f"ANPR-R{i + 1:07d}"
        row["synthetic"] = True
    return rows


def planted_reads(ctx: Ctx, cams: list[dict], sightings: list[dict]) -> list[dict]:
    """sightings: [{plate, at, lat, lon, crime_id, minutes: (lo, hi) or fixed camera/at}] -> reads."""
    r = ctx.rng("anpr-planted")
    out = []
    by_id = {c["camera_id"]: c for c in cams}
    for s in sightings:
        if s.get("camera_id"):
            cam = by_id[s["camera_id"]]
            at = s["at"]
        else:
            near = sorted(cams, key=lambda c: km(s["lat"], s["lon"], c["lat"], c["lon"]))[:4]
            cam = r.choice([c for c in near if km(s["lat"], s["lon"], c["lat"], c["lon"]) <= 6] or near[:1])
            at = s["at"] + timedelta(minutes=r.randint(*s["minutes"]), seconds=r.randint(0, 59))
        out.append({"camera_id": cam["camera_id"], "read_at": at, "plate_text": s["plate"].replace(" ", ""),
                    "plate_confidence": s.get("confidence") or round(r.uniform(0.7, 0.92), 2),
                    "direction": s.get("direction") or r.choice(["N", "S", "E", "W"]), "lat": cam["lat"],
                    "lon": cam["lon"], "h3_r9": cam["h3_r9"], "crime_id": s.get("crime_id")})
    return out


# ---------- 112 calls ----------
def calls(ctx: Ctx, drafts: list[dict], n: int) -> list[dict]:
    r = ctx.rng("calls")
    rows = []
    for d in sorted(drafts, key=lambda x: x["crime_id"]):
        if r.random() > 0.7 or d.get("dq") == "dq_time_inconsistent":
            continue
        lat, lon = offset(d["lat"], d["lon"], r.uniform(0, 0.3), r.uniform(0, 360))
        span = max(1, int((d["reported_at"] - d["occurred_from"]).total_seconds() // 60))
        at = d["occurred_from"] + timedelta(minutes=r.randint(1, min(30, span)), seconds=r.randint(0, 59))
        rows.append({"received_at": at, "caller": "masked", "category": d["sub_type"], "lat": round(lat, 6),
                     "lon": round(lon, 6), "dispatched_unit": f"PATROL-{d['station'].code}-{r.randint(1, 8):02d}",
                     "outcome": "fir_registered", "fir_ref": d["fir_no"], "crime_id": d["crime_id"]})
    days = ctx.days()
    while len(rows) < n:
        lat, lon, _, _, st = C.place(r, ctx, {"residential": 3, "bus_stop": 2, "market": 1, "hospital": 1})
        hour = C.pick_hour(r, [[7, 23, 3], [23, 24, 1], [0, 7, 1]])
        rows.append({"received_at": ctx.local(r.choice(days), hour) + timedelta(seconds=r.randint(0, 59)),
                     "caller": "masked", "category": r.choice(CALL_NOISE), "lat": lat, "lon": lon,
                     "dispatched_unit": f"PATROL-{st.code}-{r.randint(1, 8):02d}" if r.random() < 0.8 else None,
                     "outcome": r.choice(["attended", "no_action", "referred", "attended"]), "fir_ref": None,
                     "crime_id": None})
    rows.sort(key=lambda x: (x["received_at"], x["lat"], x["lon"]))
    for row in rows:
        row["call_id"] = f"C112-{row['received_at']:%Y-%m-%d}-{abs(hash_int(row)) % 100000:05d}"
        row["cell"] = cells(row["lat"], row["lon"])["h3_r9"]
        row["synthetic"] = True
    seen: dict[str, int] = {}
    for row in rows:  # make ids unique, deterministically
        k = row["call_id"]
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            row["call_id"] = f"{k}-{seen[k]}"
    return rows


def hash_int(row: dict) -> int:
    import hashlib

    h = hashlib.sha256(f"{row['received_at'].isoformat()}|{row['lat']}|{row['lon']}|{row['category']}".encode())
    return int.from_bytes(h.digest()[:6], "big")


# ---------- persons, releases, history sheets ----------
def persons_and_registers(ctx: Ctx, drafts: list[dict], returns: list[dict], n_persons: int,
                          n_releases: int, n_sheets: int) -> dict:
    r = ctx.rng("persons")
    nm = ctx.names
    gcc = [w[0] for w in ctx.wards if w[0] != 0]

    def name(female: bool) -> str:
        return f"{r.choice(nm['initials'])}. {r.choice(nm['female'] if female else nm['male'])}"

    persons, links = [], []
    # 1. offender-return people first (stable ids P-9xxxx)
    for ret in returns:
        persons.append({"person_id": ret["person_ref"], "name": name(False), "aliases": [],
                        "descriptors": {"build": r.choice(C.BUILDS), "height_band": r.choice(["160-170", "170-180"]),
                                        "marks": r.choice(ctx.series_cfg["generated"]["signatures"]["distinctive"])},
                        "residence_ward": ret["ward_no"], "source": "sb.persons", "synthetic": True})
    # 2. accused for solved cases
    solved = [d for d in sorted(drafts, key=lambda x: x["crime_id"]) if d["status"] in ("charge_sheeted", "closed")]
    i = 0
    for d in solved:
        for _ in range(1 if r.random() < 0.7 else 2):
            i += 1
            pid = f"P-{i:05d}"
            persons.append({"person_id": pid, "name": name(r.random() < 0.08),
                            "aliases": [r.choice(nm["male"])] if r.random() < 0.3 else [],
                            "descriptors": {"build": r.choice(C.BUILDS)}, "residence_ward": r.choice(gcc),
                            "source": "sb.persons", "synthetic": True})
            links.append({"person_id": pid, "crime_id": d["crime_id"], "role": "accused", "synthetic": True})
            if len(persons) >= n_persons:
                break
        if len(persons) >= n_persons:
            break
    while len(persons) < n_persons:
        i += 1
        persons.append({"person_id": f"P-{i:05d}", "name": name(r.random() < 0.2), "aliases": [],
                        "descriptors": {}, "residence_ward": r.choice(gcc), "source": "sb.persons", "synthetic": True})
    for p in persons:
        p["source_row_id"] = p["person_id"]

    pool = [p for p in persons if not p["person_id"].startswith("P-9")]
    releases, sheets = [], []
    for ret in returns:
        releases.append({"release_id": f"REL-R{ret['return_id'][3:]}", "person_ref": ret["person_ref"],
                         "released_on": ret["released_on"].isoformat(), "release_type": "bail",
                         "prior_mo_tags": ";".join(ret["mo_tags"]), "residence_ward": ret["ward_no"],
                         "station_of_residence": ret["station_of_residence"], "synthetic": True})
        sheets.append({"sheet_id": f"HS-R{ret['return_id'][3:]}", "person_ref": ret["person_ref"],
                       "station_id": ret["station_of_residence"],
                       "opened_on": (ctx.start - timedelta(days=r.randint(800, 2000))).isoformat(),
                       "category": "property_offender", "mo_tags": ";".join(ret["mo_tags"]),
                       "residence_ward": ret["ward_no"], "active": True, "synthetic": True})
    types = sorted(ctx.cfg["crime_types"])
    sig = ctx.series_cfg["generated"]["signatures"]["approaches"]
    for k in range(n_releases - len(releases)):
        p = r.choice(pool)
        t = r.choice(types)
        tags = [t] + ([r.choice(sig[t])] if t in sig else [])
        st = r.choice(ctx.stations)
        releases.append({"release_id": f"REL-{k + 1:04d}", "person_ref": p["person_id"],
                         "released_on": (ctx.start + timedelta(days=r.randint(0, (ctx.end - ctx.start).days))).isoformat(),
                         "release_type": r.choice(["bail", "bail", "sentence_complete", "parole", "acquitted"]),
                         "prior_mo_tags": ";".join(tags), "residence_ward": p["residence_ward"],
                         "station_of_residence": st.station_id, "synthetic": True})
    for k in range(n_sheets - len(sheets)):
        p = r.choice(pool)
        t = r.choice(types)
        sheets.append({"sheet_id": f"HS-{k + 1:04d}", "person_ref": p["person_id"], "station_id": r.choice(ctx.stations).station_id,
                       "opened_on": (ctx.start - timedelta(days=r.randint(30, 3000))).isoformat(),
                       "category": r.choice(["rowdy", "property_offender", "habitual_offender"]),
                       "mo_tags": ";".join([t] + ([r.choice(sig[t])] if t in sig else [])),
                       "residence_ward": p["residence_ward"], "active": r.random() < 0.8, "synthetic": True})
    persons.sort(key=lambda p: p["person_id"])
    links.sort(key=lambda x: (x["crime_id"], x["person_id"]))
    return {"persons": persons, "person_links": links,
            "releases": sorted(releases, key=lambda x: x["release_id"]),
            "history_sheets": sorted(sheets, key=lambda x: x["sheet_id"])}


# ---------- legacy CCTNS + archive ----------
def legacy(ctx: Ctx, n_cctns: int, n_archive: int, returns: list[dict]) -> dict:
    """Pre-window records in two other shapes. Returns {cctns: {ps_code: rows}, archive: rows, dq: [...]}."""
    r = ctx.rng("legacy")
    stations = sorted(r.sample(ctx.stations, 8), key=lambda s: s.station_id)
    ps_code = {s.station_id: 3100 + i * 7 for i, s in enumerate(stations)}
    types = sorted(ctx.cfg["crime_types"])
    shares = [ctx.cfg["crime_types"][t]["share"] for t in types]
    ipc = {r2["bns_code"]: r2["ipc_code"] for r2 in ctx.section_rows if r2["bns_code"] and r2["ipc_code"]}
    cutover = datetime(2024, 7, 1, tzinfo=ctx.tz)
    io_names = [f"{rk} {ini}. {nm}" for rk in ctx.names["io_ranks"] for ini in ctx.names["initials"][:5]
                for nm in ctx.names["male"][:6]]
    lo, hi = ctx.start - timedelta(days=480), ctx.start - timedelta(days=1)
    out: dict[int, list] = {}
    dq = []
    fir = {s.station_id: 0 for s in stations}
    rows_all = []
    for k in range(n_cctns):
        t = r.choices(types, weights=shares)[0]
        st = r.choice(stations)
        tcfg = ctx.cfg["crime_types"][t]
        for _ in range(30):
            try:
                lat, lon, anchor, name, s2 = C.place(r, ctx, tcfg["anchors"], near=(st.lat, st.lon), radius_km=2.5)
            except RuntimeError:  # no anchor of this kind near the station
                lat, lon, anchor, name, s2 = C.place(r, ctx, {"residential": 1}, near=(st.lat, st.lon), radius_km=2.5)
            if s2.station_id == st.station_id:
                break
        day = lo + timedelta(days=r.randint(0, (hi - lo).days))
        occ_from, occ_to, reported = C.times(r, ctx, tcfg, day, C.pick_hour(r, tcfg["hours"]))
        d = {"ctype": t, "sub_type": t, "role": "legacy", "series_id": None, "station": st, "lat": lat, "lon": lon,
             "anchor": anchor, "address": C.address(r, st, anchor, name), "occurred_from": occ_from,
             "occurred_to": occ_to, "reported_at": reported}
        d.update(C.describe(r, ctx, t))
        d["victims"] = C.victims_for(r, t)
        d["property"] = C.property_for(r, t, d["vehicles"])
        d["sections"] = [{"code": c} for c in tcfg["sections"]]
        text = C.narrative(r, d)
        codes = tcfg["sections"]
        act = ", ".join(ipc.get(c, c) for c in codes) if occ_from < cutover else ", ".join(codes)
        if k % 150 == 7:  # planted: sections the map does not know
            act = r.choice(["IPC 999", "SEC 41 CITY POLICE ACT", "IPC 379A", "TNPPDL ACT 3"])
            dq.append({"rule": "dq_unmapped_sections", "source": "s3csv.cctns", "row_id": None, "_k": len(rows_all)})
        fir[st.station_id] += r.randint(3, 20)
        rows_all.append((ps_code[st.station_id], {
            "PS_CODE": str(ps_code[st.station_id]), "FIR_NUM": f"{fir[st.station_id]:04d}/{reported.year}",
            "FIR_DT": reported.strftime("%d-%m-%Y"), "OCC_DT_FROM": occ_from.strftime("%d-%m-%Y %H:%M"),
            "OCC_DT_TO": occ_to.strftime("%d-%m-%Y %H:%M"), "ACT_SEC": act, "MAJOR_HEAD": MAJOR_HEAD[tcfg["category"]],
            "MINOR_HEAD": t.replace("_", " ").upper(), "PLACE_OCC": d["address"].upper(),
            "LAT": f"{lat:.4f}", "LONG": f"{lon:.4f}", "BRIEF_FACTS": text.upper()[:300],
            "PROP_STOLEN_RS": str(sum(p.get("value_inr", 0) for p in d["property"])),
            "IO_NAME": r.choice(io_names).upper()}))
    for ps, row in rows_all:
        out.setdefault(ps, []).append(row)
    for i, item in enumerate(dq):
        ps, row = rows_all[item.pop("_k")]
        item["row_id"] = f"{ps}:{row['FIR_NUM']}"
    stations_map = {str(v): k for k, v in ps_code.items()}

    # archive: another schema, older still; offender-return priors go here
    arc = []
    alo, ahi = ctx.start - timedelta(days=1500), ctx.start - timedelta(days=481)
    for ret in returns:
        for j, p in enumerate(ret["prior"]):
            st = ctx.station_at(p["lat"], p["lon"]) or min(ctx.stations, key=lambda s: km(p["lat"], p["lon"], s.lat, s.lon))
            arc.append(_arc_row(ctx, r, st, p["ctype"], p["day"], p["hour"], p["lat"], p["lon"],
                                [p["ctype"], p["approach"]], ret["person_ref"], ipc))
    while len(arc) < n_archive:
        t = r.choices(types, weights=shares)[0]
        tcfg = ctx.cfg["crime_types"][t]
        lat, lon, anchor, name, st = C.place(r, ctx, tcfg["anchors"])
        day = alo + timedelta(days=r.randint(0, (ahi - alo).days))
        sig = ctx.series_cfg["generated"]["signatures"]["approaches"]
        arc.append(_arc_row(ctx, r, st, t, day, C.pick_hour(r, tcfg["hours"]), lat, lon,
                            [t] + ([r.choice(sig[t])] if t in sig else []), None, ipc))
    arc.sort(key=lambda x: x["case_ref"])
    seen: dict[str, int] = {}
    for row in arc:
        seen[row["case_ref"]] = seen.get(row["case_ref"], 0) + 1
        if seen[row["case_ref"]] > 1:
            row["case_ref"] += f"-{seen[row['case_ref']]}"
    return {"cctns": out, "ps_codes": stations_map, "archive": arc, "dq": dq}


def _arc_row(ctx, r, st, t, day, hour, lat, lon, tags, accused, ipc) -> dict:
    tcfg = ctx.cfg["crime_types"][t]
    when = ctx.local(day, hour)
    return {"case_ref": f"ARC/{st.code}/{when.year}/{r.randint(1, 999):03d}", "station_name": st.locality,
            "crime_head": tcfg["category"].upper(), "crime_subhead": t, "date_of_occurrence": when.strftime("%Y%m%d"),
            "time_of_occurrence": when.strftime("%H%M"), "latitude": round(lat, 5), "longitude": round(lon, 5),
            "ipc_sections": ";".join((ipc.get(c) or c).replace("IPC ", "") for c in tcfg["sections"]),
            "accused_ids": accused or "", "mo_tags": ";".join(tags),
            "property_value": sum(p.get("value_inr", 0) for p in C.property_for(r, t, [])),
            "disposal": r.choice(["convicted", "acquitted", "pending trial", "undetected", "compounded"]),
            "synthetic": True}

