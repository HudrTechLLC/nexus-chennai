"""Planted structure, part 2 (spec D2): vehicle chains, offender returns, data-quality defects.

- Vehicle chain: a two-wheeler stolen at station A is later used in robberies at station B.
  The robbery FIRs carry only a partial plate; ANPR reads of the full plate (sources.py) tie
  the theft to the use. Linked through q_vehicle_trail, not through blocking (different
  category), so app.eval should score these pairs on the vehicle factor.
- Offender return: a released, history-sheeted person whose old MO reappears near home
  within 60 days. Prior cases live in the legacy archive; the returns are new FIRs.
- DQ defects: a few FIRs placed in the sea or reported before they occurred.
"""

from __future__ import annotations

from datetime import timedelta

from data.geo import km, offset

from . import crimes as C
from .context import Ctx

CHAIN_USE_TYPES = ["chain_snatching", "street_robbery", "mobile_snatching"]
RETURN_TYPES = ["night_house_break", "chain_snatching", "two_wheeler_theft", "day_house_break", "pickpocket"]


def vehicle_chains(ctx: Ctx, pool: list[dict], n: int) -> list[dict]:
    """Returns [{theft, uses: [draft, ...], plate}] and marks the use drafts."""
    r = ctx.rng("vehicle-chains")
    thefts = [d for d in pool if d["ctype"] == "two_wheeler_theft" and d["role"] == "background"
              and (ctx.end - d["occurred_from"].date()).days > 40]
    out = []
    for i, theft in enumerate(r.sample(thefts, n)):
        stolen = next(v for v in theft["vehicles"] if v["role"] == "stolen")
        uses = []
        far = [s for s in ctx.stations if s.station_id != theft["station"].station_id
               and 3 <= km(theft["lat"], theft["lon"], s.lat, s.lon) <= 12]
        st_b = r.choice(far)
        for j in range(r.randint(1, 2)):
            ctype = r.choice(CHAIN_USE_TYPES)
            tcfg = ctx.cfg["crime_types"][ctype]
            lat, lon, anchor, name, st = C.place(r, ctx, tcfg["anchors"], near=(st_b.lat, st_b.lon), radius_km=1.8)
            day = theft["occurred_from"].date() + timedelta(days=r.randint(3, 30) + 4 * j)
            occ_from, occ_to, reported = C.times(r, ctx, tcfg, min(day, ctx.end), C.pick_hour(r, tcfg["hours"]))
            d = {"ctype": ctype, "sub_type": ctype, "role": "vehicle_chain", "series_id": None,
                 "chain_id": f"VC-{i + 1:02d}", "station": st, "lat": lat, "lon": lon, "anchor": anchor,
                 "address": C.address(r, st, anchor, name), "occurred_from": occ_from, "occurred_to": occ_to,
                 "reported_at": reported}
            d.update(C.describe(r, ctx, ctype))
            d["vehicles"] = [{"role": "used_by_offender", "type": "motorcycle", "make_model": stolen["make_model"],
                              "colour": stolen["colour"], "plate": C.partial(r, stolen["plate"])}]
            d["offenders"][0]["count"] = 2
            d["mo"]["offender_count"] = 2
            uses.append(C.finish(r, ctx, d))
        out.append({"chain_id": f"VC-{i + 1:02d}", "theft": theft, "uses": uses, "plate": stolen["plate"]})
    return out


def offender_returns(ctx: Ctx, n: int) -> list[dict]:
    """Released offenders whose MO returns within 60 days near their ward.

    Returns [{return_id, person, release, prior: [legacy draft], returns: [draft]}]. The person and
    release rows are finished in sources.py, which also writes the prior cases into the archive."""
    r = ctx.rng("offender-returns")
    out = []
    gcc = [w for w in ctx.wards if w[0] != 0]
    sig = ctx.series_cfg["generated"]["signatures"]
    for i in range(n):
        ctype = RETURN_TYPES[i % len(RETURN_TYPES)]
        tcfg = ctx.cfg["crime_types"][ctype]
        ward_no, _, wg = r.choice(gcc)
        home = wg.representative_point()
        released = ctx.start + timedelta(days=r.randint(60, (ctx.end - ctx.start).days - 70))
        approach = r.choice(sig["approaches"].get(ctype) or ["unknown"])
        person_ref = f"P-9{i + 1:04d}"
        mo_tags = [ctype, approach]
        returns = []
        for j in range(2):
            lat, lon, anchor, name, st = C.place(r, ctx, tcfg["anchors"], near=(home.y, home.x), radius_km=1.5)
            day = released + timedelta(days=r.randint(5, 55))
            occ_from, occ_to, reported = C.times(r, ctx, tcfg, min(day, ctx.end), C.pick_hour(r, tcfg["hours"]))
            d = {"ctype": ctype, "sub_type": ctype, "role": "offender_return", "series_id": None,
                 "return_id": f"OR-{i + 1:02d}", "station": st, "lat": lat, "lon": lon, "anchor": anchor,
                 "address": C.address(r, st, anchor, name), "occurred_from": occ_from, "occurred_to": occ_to,
                 "reported_at": reported}
            d.update(C.describe(r, ctx, ctype))
            d["mo"]["approach"] = approach
            returns.append(C.finish(r, ctx, d))
        prior = []
        for j in range(r.randint(2, 3)):
            day = ctx.start - timedelta(days=r.randint(400, 1300))
            lat, lon = offset(home.y, home.x, r.uniform(0.3, 2.0), r.uniform(0, 360))
            prior.append({"ctype": ctype, "approach": approach, "day": day, "hour": C.pick_hour(r, tcfg["hours"]),
                          "lat": round(lat, 6), "lon": round(lon, 6)})
        out.append({"return_id": f"OR-{i + 1:02d}", "person_ref": person_ref, "ward_no": ward_no,
                    "home": (home.y, home.x), "released_on": released, "mo_tags": mo_tags,
                    "returns": returns, "prior": prior,
                    "station_of_residence": (ctx.station_at(home.y, home.x) or returns[0]["station"]).station_id})
    return out


def dq_defects(ctx: Ctx, pool: list[dict]) -> list[dict]:
    """Mutate a few background FIRs into known DQ defects; returns [{rule, crime_key}]."""
    r = ctx.rng("dq-defects")
    bg = [d for d in pool if d["role"] == "background"]
    picks = r.sample(bg, 10)
    out = []
    for d in picks[:5]:  # in the sea, east of the coastline
        d["lat"], d["lon"] = round(d["lat"], 6), round(80.33 + r.uniform(0.01, 0.05), 6)
        d["dq"] = "dq_bad_geo"
        out.append({"rule": "dq_bad_geo", "crime_key": d["_key"]})
    for d in picks[5:]:  # reported before it occurred
        d["reported_at"] = d["occurred_from"] - timedelta(hours=r.randint(2, 30))
        d["dq"] = "dq_time_inconsistent"
        out.append({"rule": "dq_time_inconsistent", "crime_key": d["_key"]})
    return out
