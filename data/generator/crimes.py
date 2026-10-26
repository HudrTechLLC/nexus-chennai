"""Build one synthetic crime: time, place, MO, vehicles, people, property, narrative, statements.

A crime here is a *draft* dict carrying its ground truth (mo, signature, series) next to the
public fields. The writer splits it: public fields go to the Supabase rows, truth to _truth/.
Narratives state the MO in plain words, because the Extractor (Nemotron) reads only text.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from data.geo import cells, km, offset

from .context import Ctx, Station

# ---------- vocabulary ----------
APPROACH_TEXT = {
    "two_wheeler_from_behind": "came from behind on a two-wheeler",
    "asked_for_directions": "stopped on a two-wheeler and asked for directions",
    "posed_as_courier": "came on a two-wheeler posing as a courier delivery man",
    "on_foot_snatch_and_run": "walked up on foot, snatched it and ran",
    "auto_pillion": "came in an autorickshaw and the passenger reached out",
    "window_grille_cut": "cut the window grille to get in",
    "door_lock_broken": "broke the front door lock",
    "back_door_pried": "prised open the back door",
    "roof_sheet_removed": "removed the roof sheets to get in",
    "posed_as_eb_staff": "came posing as electricity board staff to check the meter",
    "posed_as_gas_delivery": "came posing as gas cylinder delivery staff",
    "duplicate_key": "used a duplicate key",
    "handle_lock_broken": "broke the handle lock",
    "wire_bypass": "bypassed the ignition wires",
    "knife_threat_two_men": "threatened with a knife",
    "auto_lure": "offered a lift in an autorickshaw and then robbed",
    "fake_police_check": "stopped the victim claiming to be police checking documents",
    "crowd_jostle": "jostled in the crowd",
    "bus_door_press": "pressed close near the bus door",
    "distraction_by_spill": "spilled something on the victim as a distraction",
    "distraction_pair": "one distracted the staff while the other took the goods",
    "fake_bill_swap": "swapped the bill with a fake one",
    "trial_room_switch": "switched items in the trial room",
    "atm_card_swap": "offered help at the ATM and swapped the card",
    "fake_kyc_call": "phoned claiming to be bank staff updating KYC",
    "gold_loan_fraud": "pledged fake gold for a loan",
    "fake_ride_hailing_cab": "posed as a ride-hailing cab and picked up the victim",
    "acquaintance_lure": "lured the victim, who knew him, to a quiet place",
    "argument_escalated": "an argument turned violent",
    "followed_repeatedly": "followed the victim repeatedly",
    "took_from_school_gate": "took the child from near the school gate",
    "unknown": "acted in a way the complainant could not describe",
}
DEFAULT_APPROACH = {
    "assault": ["argument_escalated"], "murder": ["argument_escalated", "acquaintance_lure"],
    "attempt_murder": ["argument_escalated"], "stalking": ["followed_repeatedly"],
    "kidnapping": ["took_from_school_gate"], "car_theft": ["duplicate_key", "wire_bypass"],
    "cab_robbery": ["fake_ride_hailing_cab"],
}
TARGET = {
    "chain_snatching": ("lone_pedestrian_woman", "gold_chain"), "mobile_snatching": ("pedestrian", "mobile_phone"),
    "street_robbery": ("lone_pedestrian", "cash_and_phone"), "cab_robbery": ("lone_passenger", "cash_and_phone"),
    "night_house_break": ("locked_house", "gold_jewellery"), "day_house_break": ("occupied_house", "gold_jewellery"),
    "two_wheeler_theft": ("parked_two_wheeler", "two_wheeler"), "car_theft": ("parked_car", "car"),
    "shop_theft": ("shop", "goods"), "pickpocket": ("commuter", "wallet"), "cheating": ("account_holder", "cash"),
    "assault": ("individual", "none"), "stalking": ("woman", "none"), "murder": ("individual", "none"),
    "attempt_murder": ("individual", "none"), "kidnapping": ("child", "none"),
}
TWO_WHEELER_TYPES = {"chain_snatching", "mobile_snatching", "street_robbery"}
COLOURS = ["black", "blue", "grey", "white", "red", "maroon", "silver", "green"]
MOTORCYCLES = ["Honda Shine", "Hero Splendor", "TVS Apache", "Bajaj Pulsar 150", "Yamaha FZ", "Honda Activa",
               "Suzuki Access", "TVS Jupiter"]
CARS = ["Maruti Swift", "Hyundai i10", "Maruti Swift Dzire", "Toyota Innova", "Honda City", "Tata Nexon"]
HELMETS = ["black", "white", "red", "blue open-face", "grey", "no helmet"]
BUILDS = ["thin", "medium", "heavy"]
AGE_BANDS = ["18-20", "20-30", "30-40", "40-50"]
PLATE_DISTRICTS = [f"{n:02d}" for n in list(range(1, 23)) + list(range(85, 100))]
NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four"}


def plate(rng: random.Random, district: str | None = None) -> str:
    d = district or rng.choice(PLATE_DISTRICTS)
    series = rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") + rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ")
    return f"TN {d} {series} {rng.randint(1, 9999):04d}"


def partial(rng: random.Random, full: str) -> str:
    """What a witness or a blurry camera got: some characters unread (?)."""
    _, d, s, n = full.split()
    pick = rng.random()
    if pick < 0.4:
        return f"TN {d} ?? {n}"
    if pick < 0.7:
        return f"TN {d} {s[0]}? {n}"
    if pick < 0.85:
        return f"?? {n}"
    return f"TN {d} {s} {n[:2]}??"


# ---------- time ----------
def pick_hour(rng: random.Random, bands: list[list[float]]) -> float:
    weights = [(b[1] - b[0]) * b[2] for b in bands]
    b = rng.choices(bands, weights=weights)[0]
    return rng.uniform(b[0], b[1])


def pick_day(rng: random.Random, ctx: Ctx, tcfg: dict) -> date:
    days = ctx.days()
    boost = tcfg.get("festival_boost", 1.0)
    w = [boost if d in ctx.festival_days else 1.0 for d in days]
    return rng.choices(days, weights=w)[0]


def times(rng: random.Random, ctx: Ctx, tcfg: dict, day: date, hour: float) -> tuple[datetime, datetime, datetime]:
    occ_from = ctx.local(day, hour)
    occ_to = occ_from + timedelta(minutes=rng.randint(*tcfg["duration_min"]))
    reported = occ_to + timedelta(minutes=rng.randint(*tcfg["report_delay_min"]))
    return occ_from, occ_to, reported


# ---------- place ----------
def _ward_point(rng: random.Random, ctx: Ctx) -> tuple[float, float]:
    _, _, g = rng.choice(ctx.wards)
    minx, miny, maxx, maxy = g.bounds
    from shapely.geometry import Point

    for _ in range(50):
        lon, lat = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if g.contains(Point(lon, lat)):
            return lat, lon
    c = g.representative_point()
    return c.y, c.x


def place(rng: random.Random, ctx: Ctx, anchors: dict[str, float],
          near: tuple[float, float] | None = None, radius_km: float | None = None):
    """A point near an anchor of the given types, inside some station's jurisdiction.

    With `near`, only anchors within radius_km of that point are used (series walk, decoys)."""
    types = sorted(anchors)
    near_cache: dict[str, list] = {}

    def nearby(t: str) -> list:
        """POIs of type t within radius_km of `near`; computed once per call (box, then exact)."""
        if t not in near_cache:
            rad = radius_km or 2.0
            dlat, dlon = rad / 110.0, rad / 105.0
            box = [p for p in ctx.pois.get(t, [])
                   if abs(p[0] - near[0]) <= dlat and abs(p[1] - near[1]) <= dlon]
            near_cache[t] = [p for p in box if km(near[0], near[1], p[0], p[1]) <= rad]
        return near_cache[t]

    for _ in range(200):
        t = rng.choices(types, weights=[anchors[k] for k in types])[0]
        if t == "residential":
            if near is not None:
                lat, lon = offset(near[0], near[1], rng.uniform(0.2, radius_km or 2.0), rng.uniform(0, 360))
            else:
                lat, lon = _ward_point(rng, ctx)
            name = None
        else:
            cands = nearby(t) if near is not None else ctx.pois.get(t, [])
            if not cands:
                continue
            plat, plon, name = rng.choice(cands)
            lat, lon = offset(plat, plon, rng.uniform(0.02, 0.25), rng.uniform(0, 360))
        st = ctx.station_at(lat, lon)
        if st is not None:
            return round(lat, 6), round(lon, 6), t, name, st
    raise RuntimeError(f"could not place a point for anchors {anchors} near {near}")


def address(rng: random.Random, st: Station, anchor: str, poi_name: str | None) -> str:
    area = st.locality
    if poi_name:
        return f"near {poi_name}, {area}"
    if anchor == "residential":
        n = rng.randint(1, 12)
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th")
        return f"{n}{suffix} {rng.choice(['Cross Street', 'Main Road', 'Street', 'Avenue'])}, {area}"
    return f"near a {anchor.replace('_', ' ')}, {area}"


# ---------- people, vehicles, property ----------
def describe(rng: random.Random, ctx: Ctx, ctype: str) -> dict:
    """Random (background) MO and descriptions for a crime type."""
    sig = ctx.series_cfg["generated"]["signatures"]
    approach = rng.choice(sig["approaches"].get(ctype) or DEFAULT_APPROACH.get(ctype, ["unknown"]))
    target, item = TARGET[ctype]
    two_wheeler = ctype in TWO_WHEELER_TYPES and approach not in ("on_foot_snatch_and_run",) and rng.random() < 0.8
    count = 2 if (two_wheeler and rng.random() < 0.65) else rng.choice([1, 1, 2, 3])
    vehicles = []
    if two_wheeler:
        full = plate(rng)
        vehicles.append({"role": "used_by_offender", "type": "motorcycle", "make_model": rng.choice(MOTORCYCLES),
                         "colour": rng.choice(COLOURS), "plate": partial(rng, full) if rng.random() < 0.35 else None})
    offenders = [{"count": count, "helmet": rng.choice(HELMETS) if two_wheeler else None,
                  "build": rng.choice(BUILDS), "age_band": rng.choice(AGE_BANDS)}]
    return {
        "mo": {"approach": approach, "offender_count": count, "target": target, "target_item": item,
               "escape": "two_wheeler" if two_wheeler else rng.choice(["on_foot", "auto", "unknown"]),
               "violence": rng.choice(["none", "push", "threat"]) if "snatching" in ctype or "robbery" in ctype
               else "none", "place_type": [], "disguise": ["helmet"] if two_wheeler else []},
        "vehicles": vehicles, "offenders": offenders, "signature": None, "weapon": None,
    }


def victims_for(rng: random.Random, ctype: str) -> list[dict]:
    if ctype in ("shop_theft", "cheating") and rng.random() < 0.3:
        return []
    female = {"chain_snatching": 0.95, "stalking": 1.0, "mobile_snatching": 0.55}.get(ctype, 0.4)
    return [{"gender": "F" if rng.random() < female else "M",
             "age_band": rng.choice(["20-30", "30-40", "40-50", "50-60", "60-70"])}]


def property_for(rng: random.Random, ctype: str, vehicles: list[dict]) -> list[dict]:
    if ctype == "chain_snatching":
        w = rng.randint(8, 40)
        return [{"type": "gold_chain", "weight_g": w, "value_inr": w * rng.randint(6000, 6600)}]
    if ctype in ("mobile_snatching", "pickpocket"):
        return [{"type": "mobile_phone" if ctype == "mobile_snatching" or rng.random() < 0.5 else "wallet_cash",
                 "value_inr": rng.randint(800, 80000)}]
    if ctype in ("street_robbery", "cab_robbery"):
        return [{"type": "cash", "value_inr": rng.randint(500, 25000)},
                {"type": "mobile_phone", "value_inr": rng.randint(8000, 70000)}]
    if ctype in ("night_house_break", "day_house_break"):
        w = rng.randint(10, 200)
        return [{"type": "gold_jewellery", "weight_g": w, "value_inr": w * rng.randint(6000, 6600)},
                {"type": "cash", "value_inr": rng.randint(0, 80000)}]
    if ctype == "two_wheeler_theft":
        return [{"type": "two_wheeler", "value_inr": rng.randint(30000, 150000)}]
    if ctype == "car_theft":
        return [{"type": "car", "value_inr": rng.randint(300000, 1200000)}]
    if ctype == "shop_theft":
        return [{"type": "goods", "value_inr": rng.randint(2000, 90000)}]
    if ctype == "cheating":
        return [{"type": "cash", "value_inr": rng.randint(10000, 500000)}]
    return []


# ---------- text ----------
def _when(dt: datetime) -> str:
    return dt.strftime("%d-%m-%Y at about %H:%M")


def _helmet(h: str) -> str:
    """'black with red stripe' -> 'a black helmet with red stripe'; 'red' -> 'a red helmet'."""
    if " with " in h:
        colour, rest = h.split(" with ", 1)
        return f"a {colour} helmet with {rest}"
    return f"a {h} helmet"


def _person(v: dict | None) -> str:
    if not v:
        return "the complainant"
    lo = int(v["age_band"].split("-")[0])
    return f"the complainant, a {'woman' if v['gender'] == 'F' else 'man'} aged about {lo + 5},"


def narrative(rng: random.Random, d: dict) -> str:
    mo, off = d["mo"], d["offenders"][0] if d["offenders"] else {}
    who = _person(d["victims"][0] if d["victims"] else None)
    parts = [f"On {_when(d['occurred_from'])}, {who} was {rng.choice(['near', 'at', 'close to'])} {d['address']}."]
    n = off.get("count") or 1
    desc = f"{NUM_WORDS.get(n, str(n))} unknown {'person' if n == 1 else 'persons'}"
    if off.get("build"):
        desc += f" of {off['build']} build"
    if off.get("age_band"):
        desc += f", aged about {off['age_band'].replace('-', ' to ')}"
    parts.append(f"{desc.capitalize()} {APPROACH_TEXT.get(mo['approach'], mo['approach'].replace('_', ' '))}.")
    for v in d["vehicles"]:
        if v["role"] == "used_by_offender":
            s = f"They used a {v['colour']} {v['make_model']} {v['type']}"
            s += f" with number plate partly read as {v['plate']}" if v.get("plate") else ", number not noted"
            parts.append(s + ".")
    if off.get("helmet") and off["helmet"] != "no helmet":
        parts.append(f"The rider wore {_helmet(off['helmet'])}.")
    if d.get("signature"):
        parts.append(f"One of them {d['signature']}.")
    if d.get("weapon"):
        parts.append({"knife": "A knife was shown to threaten.", "cutter": "A cutting tool was used.",
                      "ligature": "Death was by strangulation with a ligature."}.get(d["weapon"], ""))
    if mo.get("violence") == "push":
        parts.append("The complainant was pushed and fell.")
    for p in d["property"]:
        w = f" weighing {p['weight_g']} g" if p.get("weight_g") else ""
        parts.append(f"Lost: {p['type'].replace('_', ' ')}{w}, worth Rs {p['value_inr']:,}.")
    parts.append({"two_wheeler": "They escaped on the two-wheeler towards the main road.",
                  "car": "They drove away in the car.", "on_foot": "The offender fled on foot."}.get(mo["escape"], ""))
    return " ".join(p for p in parts if p)


def statements(rng: random.Random, d: dict, mean: float) -> list[dict]:
    """Witness statements: same facts as the crime, each witness noticing only some of them."""
    k = min(4, max(0, int(rng.gauss(mean, 0.9) + 0.5)))
    out = []
    for i in range(k):
        off = d["offenders"][0] if d["offenders"] else {}
        bits = []
        n = off.get("count")
        if n and rng.random() < 0.8:
            bits.append(f"I saw {NUM_WORDS.get(n, str(n))} {'man' if n == 1 else 'men'}")
        for v in d["vehicles"]:
            if v["role"] == "used_by_offender" and rng.random() < 0.75:
                bits.append(f"on a {v['colour']} {v['type']}" + (f", it looked like a {v['make_model']}"
                                                                 if rng.random() < 0.5 else ""))
                if v.get("plate") and rng.random() < 0.5:
                    bits.append(f"the number ended {v['plate'].split()[-1]}")
        if off.get("helmet") and rng.random() < 0.6:
            bits.append(f"{'the rider' if rng.random() < 0.5 else 'one of them'} had {_helmet(off['helmet'])}")
        if off.get("build") and rng.random() < 0.5:
            bits.append(f"{off['build']} build")
        if d.get("signature") and rng.random() < 0.6:
            bits.append(f"one of them {d['signature']}")
        if not bits:
            bits.append("I heard shouting and came out, but they had already gone")
        text = ("; ".join(bits)).capitalize() + "."
        out.append({"witness_ref": f"W-{i + 1} (masked)", "mode": "text", "text": text,
                    "recorded_at": d["reported_at"] + timedelta(hours=rng.uniform(1, 72))})
    return out


# ---------- assembly ----------
def status_for(rng: random.Random, ctx: Ctx, reported: datetime) -> str:
    age = (ctx.end - reported.date()).days
    col = 0 if age < 60 else 1
    sw = ctx.cfg["status_weights"]
    keys = sorted(sw)
    return rng.choices(keys, weights=[sw[k][col] for k in keys])[0]


def finish(rng: random.Random, ctx: Ctx, d: dict) -> dict:
    """Fill derived fields (cells, ward, week, status, sections, narrative, statements)."""
    tcfg = ctx.cfg["crime_types"][d["ctype"]]
    d.setdefault("category", tcfg["category"])
    d.setdefault("severity", tcfg["severity"])
    d.setdefault("sections", [{"code": c, "ipc_equiv": (ctx.sections.get(c) or {}).get("ipc_code") or None}
                              for c in tcfg["sections"]])
    d.setdefault("victims", victims_for(rng, d["ctype"]))
    d.setdefault("property", property_for(rng, d["ctype"], d["vehicles"]))
    d.setdefault("status", status_for(rng, ctx, d["reported_at"]))
    d["ward_no"] = ctx.ward_at(d["lat"], d["lon"])
    d.update(cells(d["lat"], d["lon"]))
    iso = d["occurred_from"].isocalendar()
    d["week"] = f"{iso[0]}-W{iso[1]:02d}"
    d.setdefault("narrative", narrative(rng, d))
    d["statements"] = statements(rng, d, ctx.cfg["statements_per_crime"])
    return d


def background(rng: random.Random, ctx: Ctx, ctype: str) -> dict:
    tcfg = ctx.cfg["crime_types"][ctype]
    lat, lon, anchor, poi_name, st = place(rng, ctx, tcfg["anchors"])
    day = pick_day(rng, ctx, tcfg)
    occ_from, occ_to, reported = times(rng, ctx, tcfg, day, pick_hour(rng, tcfg["hours"]))
    d = {"ctype": ctype, "sub_type": ctype, "role": "background", "series_id": None, "station": st,
         "lat": lat, "lon": lon, "anchor": anchor, "address": address(rng, st, anchor, poi_name),
         "occurred_from": occ_from, "occurred_to": occ_to, "reported_at": reported}
    d.update(describe(rng, ctx, ctype))
    if ctype == "two_wheeler_theft":
        d["vehicles"] = [{"role": "stolen", "type": "motorcycle", "make_model": rng.choice(MOTORCYCLES),
                          "colour": rng.choice(COLOURS), "plate": plate(rng)}]
    if ctype == "car_theft":
        d["vehicles"] = [{"role": "stolen", "type": "car", "make_model": rng.choice(CARS),
                          "colour": rng.choice(COLOURS), "plate": plate(rng)}]
    if ctype in ("street_robbery", "attempt_murder", "murder") and rng.random() < 0.4:
        d["weapon"] = "knife"
    return finish(rng, ctx, d)
