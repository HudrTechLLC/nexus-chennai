"""Seed synthetic published appeals for the public /appeals page (chief, 26 Oct). Owner: nexus-2.

    python -m data.seed_appeals             # dry run: prints the appeals it would publish
    python -m data.seed_appeals --write     # insert each as a draft, then publish it through the guard

Service role from SUPABASE_SERVICE_ROLE_KEY_FILE (default ~/.secrets/nexus-service-role.key), SUPABASE_URL
from the environment. Deterministic and idempotent: the same data picks the same cases and the same text, the
appeal id is derived from the crime id, and an appeal that is already published is left alone.

Selection: one generated case per station in STATIONS, from the last WINDOW_DAYS days before DATA_END, of a
property-crime sub-type a public appeal suits, preferring sub-types not yet used and cases with an extracted MO.
Never: the Red Pulsar series (its appeal is published on camera), the judge cases, EXCLUDE, console-filed FIRs
(not generator-made), or a case that already has an appeal.

Text: fixed templates over the case's sub-type, time band, week and a few MO fields mapped to fixed phrases
(no free text from the case: no names, streets, landmarks, plates or numbers). area_label is the station's
locality. Every appeal is checked in code with the Sanitiser's leak rules, then inserted as a draft and
published with an UPDATE, so the live publish guard (0006_02, 0007_08, 0007_09) checks it too.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.agents.sanitiser import crime_type_mismatch, iso_week, leak_kind  # noqa: E402
from app.scoring.factors import parse_ts, time_band  # noqa: E402

STATIONS = ("PS-GUINDY-J3", "PS-MAMBALAM-R1", "PS-MYLAPORE-E1", "PS-ANNANAGAR-K4", "PS-TAMBARAM-S11",
            "PS-VELACHERY-J7", "PS-KODAMBAKKAM-R2", "PS-EGMORE-F2")
DATA_END = datetime(2026, 10, 26, tzinfo=timezone.utc)  # end of the generated window (data/generated MANIFEST)
WINDOW_DAYS = 30
JUDGE = ("CHN-AD-2026-001182", "CHN-GU-2025-000945", "CHN-KU-2025-000078")
EXCLUDE = ("CHN-VL-2026-000877", "CHN-AD-2026-001231", "CHN-CM-2025-000450", "CHN-TU-2025-000437")
RED_PULSAR = "SER-RED-PULSAR"
GEN_NS = uuid.UUID("6f1c2a52-6a71-4c51-9e57-2c7b1b0a0e42")  # data/seed.py GEN_NS: generator-made crimes
SANITISER_MODEL = "seed:template"
CITY_OFFSET = timedelta(hours=5, minutes=30)  # time bands are city-local (cities/chennai timezone)

# Sub-types a public appeal suits, in preference order; violent and personal crimes are never seeded.
SUB_TYPES = ("chain_snatching", "mobile_snatching", "night_house_break", "two_wheeler_theft", "street_robbery",
             "day_house_break", "cab_robbery", "shop_theft", "pickpocket", "car_theft")

TITLE = {
    "chain_snatching": "Chain snatching in {area}",
    "mobile_snatching": "Phone snatched from a pedestrian in {area}",
    "night_house_break": "Night-time house break-in in {area}",
    "day_house_break": "Daytime house break-in in {area}",
    "two_wheeler_theft": "Two-wheeler stolen in {area}",
    "street_robbery": "Street robbery in {area}",
    "cab_robbery": "Cab driver robbed in {area}",
    "shop_theft": "Theft from a shop in {area}",
    "pickpocket": "Pickpocketing in {area}",
    "car_theft": "Car stolen in {area}",
}
WHAT = {
    "chain_snatching": "a woman's gold chain was snatched", "mobile_snatching": "a mobile phone was snatched",
    "night_house_break": "a house was broken into", "day_house_break": "a locked house was broken into",
    "two_wheeler_theft": "a parked two-wheeler was stolen", "street_robbery": "a person was robbed on the street",
    "cab_robbery": "a cab driver was robbed by passengers", "shop_theft": "goods were stolen from a shop",
    "pickpocket": "a wallet was taken from a pedestrian", "car_theft": "a parked car was stolen",
}
# MO values -> fixed phrases. A value matching no rule adds nothing (never echoed).
APPROACH = (("from_behind", "came up from behind on a two-wheeler"), ("grille", "got in by cutting a window grille"),
            ("cab", "posed as a ride-hailing cab"), ("police", "claimed to be police checking documents"),
            ("autorickshaw", "arrived in an autorickshaw"), ("on_foot", "approached on foot"))
ESCAPE = (("two_wheeler", "rode off on a two-wheeler"), ("motorcycle", "rode off on a motorcycle"),
          ("foot", "left on foot"), ("ran", "left on foot"))
DISGUISE = (("helmet", "wore {a}helmet{s}"), ("courier", "dressed as {a}delivery rider{s}"))
COUNT = {1: "One person", 2: "Two people", 3: "Three people"}
ITEM = (("gold_chain", "a gold chain"), ("mobile", "a mobile phone"), ("jewellery", "gold jewellery"))
# What a stolen item would be offered as, when the MO names none.
ITEM_BY_TYPE = {"night_house_break": "jewellery or valuables", "day_house_break": "jewellery or valuables",
                "two_wheeler_theft": "a two-wheeler", "car_theft": "a car", "shop_theft": "shop goods"}


def _first(value: Any, rules: tuple[tuple[str, str], ...]) -> str | None:
    for v in value if isinstance(value, list) else [value]:
        for needle, phrase in rules:
            if v and needle in str(v).lower():
                return phrase
    return None


def appeal_id(crime_id: str, year: int) -> str:
    return f"PI-{year}-{hashlib.sha256(('seed:' + crime_id).encode()).hexdigest()[:6].upper()}"


def locality(station_name: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", station_name).strip()


def build(case: dict[str, Any], station_name: str, mo: dict[str, Any] | None) -> dict[str, Any]:
    """The public appeal for one case: templates only."""
    st = case["sub_type"]
    ts = parse_ts(case["occurred_from"])
    band = time_band(ts + CITY_OFFSET if ts.tzinfo is None else ts.astimezone(timezone(CITY_OFFSET)))
    area = locality(station_name)
    mo = mo or {}
    n = int(mo["offender_count"]) if str(mo.get("offender_count") or "").isdigit() else 0
    who = COUNT.get(n)
    approach, escape = _first(mo.get("approach"), APPROACH), _first(mo.get("escape"), ESCAPE)
    if approach and escape and "two-wheeler" in approach and escape.startswith("rode off"):
        escape = "rode away"  # "came up ... on a two-wheeler and rode off on a two-wheeler" reads twice
    disguise = _first(mo.get("disguise"), DISGUISE)
    if disguise:
        disguise = disguise.format(a="a " if n == 1 else "", s="" if n == 1 else "s")
    acts = [p for p in (approach, disguise, escape) if p]
    summary = f"One {band} in {area}, {WHAT[st]}."
    if who and acts:
        summary += f" {who} {', '.join(acts[:-1]) + ' and ' if len(acts) > 1 else ''}{acts[-1]}."
    summary += " Police are asking anyone who saw something to share it. Tips can be anonymous."
    looking = [f"Anyone who was in {area} in the {band} and saw something unusual",
               f"Shop or home CCTV covering main roads in {area} during the {band}"]
    if any(k in st for k in ("snatch", "robbery", "pickpocket")) and _first(mo.get("escape"), ESCAPE):
        looking.append("Sightings of riders leaving the area quickly on a two-wheeler"
                       if "rode" in _first(mo.get("escape"), ESCAPE) else "Sightings of people running from the area")
    item = _first(mo.get("target_item"), ITEM) or ITEM_BY_TYPE.get(st)
    if item:
        looking.append(f"Anyone offered {item} for sale soon after")
    return {
        "public_incident_id": appeal_id(case["crime_id"], ts.year),
        "crime_id": case["crime_id"],
        "title": TITLE[st].format(area=area),
        "category": case["category"],
        "area_label": area,
        "cell": case["h3_r8"],
        "week": iso_week(ts),
        "time_window": band.title(),
        "summary": summary,
        "looking_for": looking,
        "images": [],
        "approved_by": f"station_officer:{case['station_id']}",
        "sanitiser_model": SANITISER_MODEL,
        "synthetic": True,
    }


def problems(a: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """Code-side check before the database guard: pattern leaks and crime-type mismatches."""
    out = []
    for field in ("title", "summary", "area_label", *[f"looking_for[{i}]" for i in range(len(a["looking_for"]))]):
        text = a["looking_for"][int(field[12:-1])] if field.startswith("looking_for") else a[field]
        if leak_kind(text):
            out.append(f"{field}: {leak_kind(text)}")
        if crime_type_mismatch(text, case["sub_type"]):
            out.append(f"{field}: names {crime_type_mismatch(text, case['sub_type'])}")
        for k in ("crime_id", "fir_no", "station_id", "address"):
            if case.get(k) and str(case[k]).lower() in text.lower():
                out.append(f"{field}: contains {k}")
    return out


# ---------------------------------------------------------------------------- Supabase (PostgREST)

class Rest:
    def __init__(self) -> None:
        url = os.environ.get("SUPABASE_URL") or ""
        key_file = Path(os.path.expanduser(os.environ.get("SUPABASE_SERVICE_ROLE_KEY_FILE",
                                                          "~/.secrets/nexus-service-role.key")))
        if not url or not key_file.is_file():
            raise SystemExit("set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY_FILE (the key is read from the file)")
        key = key_file.read_text(encoding="utf-8").strip()
        self.c = httpx.Client(base_url=url.rstrip("/") + "/rest/v1", timeout=60,
                              headers={"apikey": key, "Authorization": f"Bearer {key}"})

    def get(self, table: str, **params: str) -> list[dict[str, Any]]:
        r = self.c.get(f"/{table}", params=params)
        r.raise_for_status()
        return r.json()


def select(rest: Rest) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    since = (DATA_END - timedelta(days=WINDOW_DAYS)).isoformat()
    cols = "crime_id,source_row_id,station_id,fir_no,category,sub_type,occurred_from,h3_r8,address"
    crimes = rest.get("crimes", select=cols, station_id=f"in.({','.join(STATIONS)})", occurred_from=f"gte.{since}",
                      order="crime_id.asc", limit="5000")
    series = json.loads((ROOT / "data" / "sample" / "_truth" / "series.json").read_text(encoding="utf-8"))
    red = {c for s in series if s["series_id"] == RED_PULSAR for c in s["crime_ids"]}
    taken = {p["crime_id"] for p in rest.get("public_incidents", select="crime_id") if p.get("crime_id")}
    skip = red | set(JUDGE) | set(EXCLUDE) | taken
    ok = [c for c in crimes if c["source_row_id"] == str(uuid.uuid5(GEN_NS, c["crime_id"]))
          and c["crime_id"] not in skip and c["sub_type"] in SUB_TYPES and c.get("h3_r8")]
    feats = {f["crime_id"]: f["mo"] for f in rest.get(
        "crime_features", select="crime_id,mo", crime_id="in.(" + ",".join(c["crime_id"] for c in ok) + ")")} if ok else {}
    names = {s["station_id"]: s["name"] for s in rest.get("stations", select="station_id,name",
                                                           station_id=f"in.({','.join(STATIONS)})")}
    picked, used = [], set()
    for st in STATIONS:
        pool = [c for c in ok if c["station_id"] == st]
        if not pool:
            continue
        pool.sort(key=lambda c: (c["sub_type"] in used, c["crime_id"] not in feats, SUB_TYPES.index(c["sub_type"]),
                                 c["crime_id"]))
        case = pool[0]
        used.add(case["sub_type"])
        picked.append((case, build(case, names.get(st, st), feats.get(case["crime_id"]))))
    return picked


def publish(rest: Rest, a: dict[str, Any]) -> str:
    """Insert as a draft (or refresh an unpublished one), then publish with an UPDATE through the guard."""
    pid = a["public_incident_id"]
    have = rest.get("public_incidents", select="status", public_incident_id=f"eq.{pid}")
    if have and have[0]["status"] == "published":
        return "already published"
    draft = {**a, "status": "draft", "approved_by": None}
    r = rest.c.post("/public_incidents", json=draft,
                    headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
    if r.status_code >= 300:
        return f"draft failed: {r.status_code} {r.text[:200]}"
    r = rest.c.patch("/public_incidents", params={"public_incident_id": f"eq.{pid}"},
                     json={"status": "published", "approved_by": a["approved_by"]},
                     headers={"Prefer": "return=representation"})
    if r.status_code >= 300:
        return f"guard refused, left as draft: {r.status_code} {r.text[:200]}"
    row = (r.json() or [{}])[0]
    return f"published at {row.get('published_at')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="insert and publish (default: dry run)")
    args = ap.parse_args()
    rest = Rest()
    picked = select(rest)
    bad = 0
    for case, a in picked:
        issues = problems(a, case)
        bad += bool(issues)
        print(f"\n{a['public_incident_id']}  {case['crime_id']}  {case['station_id']}  {case['sub_type']}  "
              f"{a['week']} {a['time_window']}")
        print(f"  title:   {a['title']}\n  area:    {a['area_label']}\n  summary: {a['summary']}")
        for item in a["looking_for"]:
            print(f"  - {item}")
        if issues:
            print(f"  PROBLEMS: {issues}")
    print(f"\n{len(picked)} appeals, {bad} with problems")
    if not args.write:
        print("dry run: nothing written")
        return 0
    if bad:
        raise SystemExit("refusing to write: fix the problems above")
    for _, a in picked:
        print(a["public_incident_id"], publish(rest, a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
