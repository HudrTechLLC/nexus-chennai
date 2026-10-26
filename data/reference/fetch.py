"""Download the public inputs for a city pack into data/reference/raw/ (gitignored).

    python -m data.reference.fetch [--city chennai]

Sources and licences are listed in data/README.md. Overpass rejects POST from some
clients, so queries go as GET.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
RAW = Path(__file__).resolve().parent / "raw"
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = {"User-Agent": "nexus-chennai-build/0.1 (synthetic data; hackathon)", "Accept": "application/json"}


def overpass(query: str) -> dict:
    r = httpx.get(OVERPASS, params={"data": query}, headers=UA, timeout=420)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="chennai")
    args = ap.parse_args()
    pack = ROOT / "cities" / args.city
    cfg = yaml.safe_load((pack / "sources.yaml").read_text(encoding="utf-8"))["reference"]
    city = yaml.safe_load((pack / "city.yaml").read_text(encoding="utf-8"))
    w, s, e, n = city["map"]["bounds"]
    bbox = f"({s},{w},{n},{e})"
    RAW.mkdir(parents=True, exist_ok=True)

    for name, url in cfg["downloads"].items():
        r = httpx.get(url, headers=UA, timeout=120, follow_redirects=True)
        r.raise_for_status()
        (RAW / name).write_bytes(r.content)
        print(f"{name}: {len(r.content)} bytes")

    for name, body in cfg["overpass"].items():
        q = "[out:json][timeout:300];(" + body.replace("{bbox}", bbox) + ");out center tags;"
        data = overpass(" ".join(q.split()))
        (RAW / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {len(data['elements'])} elements")


if __name__ == "__main__":
    main()
