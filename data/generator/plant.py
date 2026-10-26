"""Planted structure (spec D2): series, decoys, duplicates. The ground truth for app.eval.

Every series is a *walk*: each member is placed within step_km and step_days of the previous
one and must share or neighbour its geohash5 cell, so every member passes the E5 blocking
(same category group, neighbouring geohash5, <= 45 days). Decoys pass blocking too but differ
in MO, so only the Skeptic can reject them.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from data.geo import geohash, gh5_block, km, offset

from . import crimes as C
from .context import Ctx, Station

BLOCK_DAYS = 45


def time_band(hour: float) -> str:
    h = hour % 24
    if h >= 22 or h < 5:
        return "night"
    if h < 9:
        return "early_morning"
    if h < 17:
        return "day"
    return "evening"


def _bearing(lat1, lon1, lat2, lon2) -> float:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _blocks(a: dict, b: dict) -> bool:
    return (abs((a["occurred_from"] - b["occurred_from"]).days) <= BLOCK_DAYS
            and gh5_block(geohash(a["lat"], a["lon"]), geohash(b["lat"], b["lon"])))


def _next_point(rng, ctx: Ctx, prev: dict, target: Station, spec: dict, anchors: dict):
    lo, hi = spec["step_km"]
    for _ in range(80):
        brg = (_bearing(prev["lat"], prev["lon"], target.lat, target.lon) + rng.uniform(-50, 50)) % 360
        dist = min(rng.uniform(lo, hi), max(0.4, km(prev["lat"], prev["lon"], target.lat, target.lon)))
        clat, clon = offset(prev["lat"], prev["lon"], dist, brg)
        try:
            lat, lon, anchor, name, st = C.place(rng, ctx, anchors, near=(clat, clon), radius_km=0.6)
        except RuntimeError:
            continue
        if gh5_block(geohash(prev["lat"], prev["lon"]), geohash(lat, lon)) and \
                km(prev["lat"], prev["lon"], lat, lon) <= hi + 1.0:
            return lat, lon, anchor, name, st
    raise RuntimeError("series walk could not find a blocking-compatible next point")


def _next_day(rng, ctx: Ctx, prev_day: date, spec: dict, direction: int) -> date | None:
    lo, hi = spec["step_days"]
    if spec.get("festival_only"):
        fest = sorted(d for d in ctx.festival_days if ctx.start <= d <= ctx.end)
        cands = [d for d in fest if lo <= (d - prev_day).days * direction <= hi]
        cands = cands or [d for d in fest if 0 <= (d - prev_day).days * direction <= hi]
        return rng.choice(cands) if cands else None
    d = prev_day + timedelta(days=direction * rng.randint(lo, hi))
    return d if ctx.start <= d <= ctx.end else None


def _member(rng, ctx: Ctx, spec: dict, ctype: str, lat, lon, anchor, name, st, day, sig: dict) -> dict:
    tcfg = ctx.cfg["crime_types"][ctype]
    hour = rng.uniform(*spec["hours"])
    occ_from, occ_to, reported = C.times(rng, ctx, tcfg, day, hour)
    d = {"ctype": ctype, "sub_type": ctype, "role": "series", "series_id": spec["series_id"], "station": st,
         "lat": lat, "lon": lon, "anchor": anchor, "address": C.address(rng, st, anchor, name),
         "occurred_from": occ_from, "occurred_to": occ_to, "reported_at": reported}
    mo = dict(sig["mo"])
    mo["time_band"] = time_band(hour)
    d["mo"] = mo
    d["offenders"] = [dict(sig["offenders"])]
    d["signature"] = sig.get("signature")
    d["weapon"] = sig.get("weapon")
    d["vehicles"] = []
    v = sig.get("vehicle")
    if v:
        seen = rng.choice(v["witnessed"])
        d["vehicles"].append({"role": "used_by_offender", "type": v["type"], "make_model": v["make_model"],
                              "colour": v["colour"], "plate": seen})
    if ctype in ("two_wheeler_theft",):
        d["vehicles"].append({"role": "stolen", "type": "motorcycle", "make_model": rng.choice(C.MOTORCYCLES),
                              "colour": rng.choice(C.COLOURS), "plate": C.plate(rng)})
    vict = sig.get("victim")
    if vict:
        ab = vict["age_band"]
        d["victims"] = [{"gender": vict["gender"], "age_band": rng.choice(ab) if isinstance(ab, list) else ab}]
    return d


def _walk(rng, ctx: Ctx, spec: dict, ctype: str, sig: dict, n: int, start: dict, direction: int,
          stations: list[Station]) -> list[dict]:
    out, prev = [], start
    for i in range(n):
        target = stations[(i + 1) % len(stations)]
        day = _next_day(rng, ctx, prev["occurred_from"].date(), spec, direction)
        if day is None:
            raise RuntimeError("series ran out of calendar")
        lat, lon, anchor, name, st = _next_point(rng, ctx, prev, target, spec, sig["anchors"])
        m = _member(rng, ctx, spec, ctype, lat, lon, anchor, name, st, day, sig)
        out.append(m)
        prev = m
    return out


def _sig_from_named(spec: dict) -> dict:
    return {"mo": spec["mo"], "offenders": spec["offenders"], "vehicle": spec.get("vehicle"),
            "weapon": spec.get("weapon") or spec.get("tool"), "victim": spec.get("victim"),
            "anchors": spec["anchors"], "signature": spec.get("signature")}


def _hero(ctx: Ctx, spec: dict, h: dict, sig: dict) -> dict:
    st = ctx.by_code[h["station"]]
    occ_from = datetime.fromisoformat(h["occurred_from"])
    hour = occ_from.hour + occ_from.minute / 60
    mo = dict(sig["mo"])
    mo["time_band"] = time_band(hour)
    v = sig["vehicle"]
    return {"ctype": spec["crime_type"], "sub_type": spec["crime_type"], "role": "series",
            "series_id": spec["series_id"], "station": st, "lat": h["lat"], "lon": h["lon"], "anchor": "bus_stop",
            "address": h["address"], "occurred_from": occ_from,
            "occurred_to": datetime.fromisoformat(h["occurred_to"]),
            "reported_at": datetime.fromisoformat(h["reported_at"]), "mo": mo,
            "offenders": [dict(sig["offenders"])], "signature": None, "weapon": None,
            "vehicles": [{"role": "used_by_offender", "type": v["type"], "make_model": v["make_model"],
                          "colour": v["colour"], "plate": h["plate_witnessed"]}],
            "victims": [h["victim"]], "property": h["property"], "fixed_id": h["crime_id"], "fixed_fir": h["fir_no"],
            "hero": True}


def named_series(rng, ctx: Ctx) -> list[tuple[dict, list[dict]]]:
    out = []
    for spec in ctx.series_cfg["named"]:
        r = ctx.rng(f"series:{spec['series_id']}")
        sig = _sig_from_named(spec)
        stations = [ctx.by_code[c] for c in spec["stations"]]
        ctype = spec["crime_type"]
        for _attempt in range(40):
            try:
                if spec.get("hero"):
                    heroes = [_hero(ctx, spec, h, sig) for h in spec["hero"]]
                    before = _walk(r, ctx, spec, ctype, sig, spec["size"] - len(heroes), heroes[0], -1, stations)
                    members = list(reversed(before)) + heroes
                else:
                    first_day = _start_day(r, ctx, spec)
                    lat, lon, anchor, name, st = C.place(r, ctx, sig["anchors"], near=(stations[0].lat, stations[0].lon),
                                                         radius_km=1.5)
                    first = _member(r, ctx, spec, ctype, lat, lon, anchor, name, st, first_day, sig)
                    members = [first] + _walk(r, ctx, spec, ctype, sig, spec["size"] - 1, first, +1, stations)
            except RuntimeError:
                continue
            if len({m["station"].station_id for m in members}) >= 2:
                break
        else:
            raise RuntimeError(f"could not plant {spec['series_id']}")
        out.append((spec, members))
    return out


def _start_day(rng, ctx: Ctx, spec: dict) -> date:
    if spec.get("festival_only"):
        fest = sorted(d for d in ctx.festival_days if ctx.start <= d <= ctx.end - timedelta(days=60))
        # earliest-first windows give a festival season room for the whole series
        return fest[rng.randrange(0, max(1, len(fest) // 3))]
    span = spec["size"] * spec["step_days"][1]
    lo, hi = ctx.start + timedelta(days=10), ctx.end - timedelta(days=min(span, 300))
    return lo + timedelta(days=rng.randint(0, max(0, (hi - lo).days)))


def generated_series(ctx: Ctx, n: int, taken_codes: set[str]) -> list[tuple[dict, list[dict]]]:
    g = ctx.series_cfg["generated"]
    sigs = g["signatures"]
    out = []
    for i in range(n):
        r = ctx.rng(f"gen-series:{i}")
        ctype = g["crime_types"][i % len(g["crime_types"])]
        tcfg = ctx.cfg["crime_types"][ctype]
        sid = f"SER-G{i + 1:02d}"
        for _attempt in range(40):
            seed_st = r.choice(ctx.stations)
            k = r.randint(*g["stations"])
            near = sorted(ctx.stations, key=lambda s: km(seed_st.lat, seed_st.lon, s.lat, s.lon))[:k]
            size = r.randint(*g["size"])
            peak = C.pick_hour(r, tcfg["hours"])
            spec = {"series_id": sid, "name": f"Generated series {i + 1}", "crime_type": ctype, "size": size,
                    "hours": [peak, peak + r.uniform(1.0, 2.5)], "step_km": g["step_km"], "step_days": g["step_days"]}
            two = ctype in C.TWO_WHEELER_TYPES
            approach = r.choice(sigs["approaches"][ctype])
            target, item = C.TARGET[ctype]
            count = 2 if two else r.choice([1, 2])
            sig = {"mo": {"approach": approach, "offender_count": count, "target": target, "target_item": item,
                          "escape": "two_wheeler" if two else "on_foot", "violence": "push" if two else "none",
                          "place_type": sorted(tcfg["anchors"])[:2], "disguise": ["helmet"] if two else []},
                   "offenders": {"count": count, "helmet": r.choice(sigs["helmets"]) if two else None,
                                 "build": r.choice(C.BUILDS), "age_band": r.choice(C.AGE_BANDS)},
                   "signature": r.choice(sigs["distinctive"]), "anchors": tcfg["anchors"], "weapon": None,
                   "victim": None}
            if two:
                full = C.plate(r)
                sig["vehicle"] = {"type": "motorcycle", "make_model": r.choice(sigs["motorcycles"]),
                                  "colour": r.choice(sigs["vehicle_colours"]), "plate": full,
                                  "witnessed": [C.partial(r, full), C.partial(r, full), None]}
            spec["true_mo"] = sig
            try:
                first_day = _start_day(r, ctx, spec)
                lat, lon, anchor, name, st = C.place(r, ctx, sig["anchors"], near=(seed_st.lat, seed_st.lon),
                                                     radius_km=1.5)
                first = _member(r, ctx, spec, ctype, lat, lon, anchor, name, st, first_day, sig)
                members = [first] + _walk(r, ctx, spec, ctype, sig, size - 1, first, +1, near)
            except RuntimeError:
                continue
            if len({m["station"].station_id for m in members}) >= 2:
                spec["stations"] = sorted({m["station"].code for m in members})
                out.append((spec, members))
                break
        else:
            raise RuntimeError(f"could not plant {sid}")
    return out


def decoys(ctx: Ctx, series: list[tuple[dict, list[dict]]], n: int) -> list[tuple[dict, list[dict]]]:
    """Near-miss clusters: same area and window as a series member, different MO."""
    out = []
    for i in range(n):
        r = ctx.rng(f"decoy:{i}")
        spec, members = series[i % len(series)]
        anchor_m = members[r.randrange(len(members))]
        ctype = spec["crime_type"]
        tcfg = ctx.cfg["crime_types"][ctype]
        cluster = []
        for j in range(r.randint(2, 3)):
            for _ in range(60):
                try:
                    lat, lon, anchor, name, st = C.place(r, ctx, tcfg["anchors"],
                                                         near=(anchor_m["lat"], anchor_m["lon"]), radius_km=2.0)
                except RuntimeError:
                    continue
                if gh5_block(geohash(anchor_m["lat"], anchor_m["lon"]), geohash(lat, lon)):
                    break
            day = anchor_m["occurred_from"].date() + timedelta(days=r.randint(-12, 12))
            day = min(max(day, ctx.start), ctx.end)
            lo, hi = spec["hours"]
            hour = (hi + r.uniform(3, 8)) % 24  # outside the series' time window
            occ_from, occ_to, reported = C.times(r, ctx, tcfg, day, hour)
            d = {"ctype": ctype, "sub_type": ctype, "role": "decoy", "series_id": None, "decoy_of": spec["series_id"],
                 "station": st, "lat": lat, "lon": lon, "anchor": anchor, "address": C.address(r, st, anchor, name),
                 "occurred_from": occ_from, "occurred_to": occ_to, "reported_at": reported}
            d.update(C.describe(r, ctx, ctype))
            series_mo = anchor_m["mo"]
            approaches = [a for a in ctx.series_cfg["generated"]["signatures"]["approaches"].get(ctype, [])
                          if a != series_mo["approach"]] or ["unknown"]
            d["mo"]["approach"] = r.choice(approaches)
            d["mo"]["time_band"] = time_band(hour)
            d["offenders"][0]["count"] = 1 if series_mo.get("offender_count", 1) != 1 else 3
            d["mo"]["offender_count"] = d["offenders"][0]["count"]
            sv = next((v for v in anchor_m["vehicles"] if v["role"] == "used_by_offender"), None)
            for v in d["vehicles"]:
                if sv and v["role"] == "used_by_offender":
                    v["colour"] = r.choice([c for c in C.COLOURS if c != sv["colour"]])
                    v["make_model"] = r.choice([m for m in C.MOTORCYCLES if m != sv["make_model"]])
                    v["plate"] = None
            cluster.append(C.finish(r, ctx, d))
        out.append(({"decoy_id": f"DEC-{i + 1:02d}", "shadows_series_id": spec["series_id"]}, cluster))
    return out


def duplicates(ctx: Ctx, pool: list[dict], n: int) -> list[tuple[dict, dict]]:
    """Same incident filed at two stations (jurisdiction dispute). Returns (original, duplicate)."""
    r = ctx.rng("duplicates")
    kinds = {"chain_snatching", "mobile_snatching", "two_wheeler_theft", "street_robbery", "night_house_break"}
    cands = [d for d in pool if d["ctype"] in kinds]
    picks = r.sample(cands, n)
    out = []
    for i, orig in enumerate(picks):
        other = min((s for s in ctx.stations if s.station_id != orig["station"].station_id),
                    key=lambda s: km(orig["lat"], orig["lon"], s.lat, s.lon))
        lat, lon = offset(orig["lat"], orig["lon"], r.uniform(0.05, 0.15), r.uniform(0, 360))
        shift = timedelta(minutes=r.randint(-15, 15))
        d = {k: v for k, v in orig.items() if k not in ("statements", "narrative", "h3_r9", "h3_r8", "geohash7",
                                                        "week", "ward_no", "status")}
        d.update(role="duplicate", dup_of=orig["_key"], station=other, lat=round(lat, 6), lon=round(lon, 6),
                 occurred_from=orig["occurred_from"] + shift, occurred_to=orig["occurred_to"] + shift,
                 reported_at=orig["reported_at"] + timedelta(hours=r.uniform(1, 6)),
                 address=C.address(r, other, orig["anchor"], None))
        out.append((orig, C.finish(r, ctx, d)))
    return out


def blocks(a: dict, b: dict) -> bool:
    return _blocks(a, b)

