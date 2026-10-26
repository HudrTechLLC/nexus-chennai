"""Synthetic export from a NEW police station, for source onboarding (WS1-23).

    python -m data.onboarding.generate_sample [--city chennai] [--out data/onboarding/sample_new_station.csv]

The file looks like another system's export: its own column names ("FIR No.", "Date of Occurrence" as dd/mm/yyyy,
"Lat/Long" in one field, "Crime Head" in its own words) and a few rows that each data-quality check should catch
(bad dates, out-of-city or swapped coordinates, missing and repeated FIR numbers, copies of existing crimes).
Everything city-specific comes from the city pack (cities/<city>/onboarding_sample.yaml); the copies of existing
crimes are read from the committed sample bundle (data/sample/sb/crimes.parquet). Deterministic (fixed seed).
Every row is synthetic and says so in "Remarks".
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261027
COLUMNS = ["FIR No.", "Date of Occurrence", "Time", "Place", "Lat/Long", "Crime Head", "Sections", "Brief Facts",
           "Status", "Remarks"]
REMARK = "Synthetic sample row (Nexus onboarding demo)"


def _pack(city: str) -> tuple[dict, dict]:
    base = ROOT / "cities" / city
    return (yaml.safe_load((base / "onboarding_sample.yaml").read_text(encoding="utf-8")),
            yaml.safe_load((base / "city.yaml").read_text(encoding="utf-8")))


def _point(rng: random.Random, lon: float, lat: float, km: float) -> tuple[float, float]:
    r = km * math.sqrt(rng.random())
    a = rng.uniform(0, 2 * math.pi)
    return (round(lat + r * math.sin(a) / 111.0, 5),
            round(lon + r * math.cos(a) / (111.0 * math.cos(math.radians(lat))), 5))


def build(city: str = "chennai") -> list[dict[str, str]]:
    spec, city_pack = _pack(city)
    rng = random.Random(SEED)
    st = spec["station"]
    lon0, lat0 = st["center"]
    start, end = (date.fromisoformat(d) for d in spec["period"])
    heads = list(spec["crime_heads"].items())
    tz = ZoneInfo(city_pack["timezone"])
    bad = spec["bad"]
    n_special = (len(bad["dates"]) + len(bad["coords"]) + bad["missing_fir_no"] + bad["repeated_fir_no"]
                 + len(bad["existing_crime_ids"]))
    rows: list[dict[str, str]] = []

    def clean_row(i: int) -> dict[str, str]:
        head, sections = heads[rng.randrange(len(heads))]
        day = start + timedelta(days=rng.randrange((end - start).days + 1))
        lat, lon = _point(rng, lon0, lat0, st["spread_km"])
        place = rng.choice(spec["places"])
        return {"FIR No.": f"{st['fir_prefix']}/{i:04d}/{day.year}", "Date of Occurrence": day.strftime("%d/%m/%Y"),
                "Time": f"{rng.randrange(24):02d}:{rng.randrange(0, 60, 5):02d}", "Place": place,
                "Lat/Long": f"{lat:.5f}, {lon:.5f}", "Crime Head": head, "Sections": sections,
                "Brief Facts": f"{head} reported near {place}; complainant gave a statement.",
                "Status": rng.choice(spec["statuses"]), "Remarks": REMARK}

    n = 1
    for _ in range(spec["rows"] - n_special):
        rows.append(clean_row(n))
        n += 1
    for d in bad["dates"]:
        r = clean_row(n)
        r["Date of Occurrence"] = d
        rows.append(r)
        n += 1
    for c in bad["coords"]:
        r = clean_row(n)
        r["Lat/Long"] = c
        rows.append(r)
        n += 1
    for _ in range(bad["missing_fir_no"]):
        r = clean_row(n)
        r["FIR No."] = ""
        rows.append(r)
        n += 1
    for k in range(bad["repeated_fir_no"]):  # the same FIR entered twice
        r = dict(rows[k * 7])
        r["Status"] = rng.choice(spec["statuses"])
        rows.append(r)
    ids = ", ".join(f"'{c}'" for c in bad["existing_crime_ids"])
    found = duckdb.sql(f"SELECT crime_id, occurred_from, lat, lon FROM '{(ROOT / 'data/sample/sb/crimes.parquet').as_posix()}' "
                       f"WHERE crime_id IN ({ids}) ORDER BY crime_id").fetchall()
    if len(found) != len(bad["existing_crime_ids"]):
        raise SystemExit("an existing crime named in onboarding_sample.yaml is not in the sample bundle")
    for _cid, occurred, lat, lon in found:  # same day, time and spot as a crime Nexus already holds
        local = occurred.astimezone(tz) if isinstance(occurred, datetime) else occurred
        r = clean_row(n)
        r.update({"Date of Occurrence": local.strftime("%d/%m/%Y"), "Time": local.strftime("%H:%M"),
                  "Lat/Long": f"{lat:.5f}, {lon:.5f}", "Crime Head": "House Breaking (Night)"})
        rows.append(r)
        n += 1
    rng.shuffle(rows)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--city", default="chennai")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "onboarding" / "sample_new_station.csv")
    a = ap.parse_args()
    rows = build(a.city)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {a.out}")


if __name__ == "__main__":
    main()
