"""Synthetic CCTV stills for the demo cases (WS1-09, spec D1 evidence_media).

    python -m data.generator.stills --from data/generated            # writes evidence/ + supabase/evidence_media.jsonl

Rendered, not photographed: a street frame drawn with Pillow (road, buildings, lamps), the
series' vehicle as a coloured silhouette, riders/figures as dark silhouettes with no faces, a
timestamp + camera-id overlay and sensor noise. Every pixel comes from a named seeded stream, so
the same generated city gives the same bytes and sha256.

Cases: every member of the judge cases' series (Red Pulsar, Grille Cutters, Night Cab), 1-3
stills each. Camera: the nearest registered CCTV camera to the scene (ref/cctv_cameras.csv).
Rows mirror what record_evidence (0007_07) writes: evidence_id = 'EV-' || <uuid>,
storage_path = <crime_id>/<uuid>.jpg (the key the storage policy parses), custody with one step,
action 'seeded'. Images are written under <gen>/evidence/ and never committed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NS = uuid.UUID("3d3f5a8e-0b5e-4f4a-9a3e-2b7c6c1d9e10")  # fixed namespace for still ids
JUDGE_IDS = ("CHN-AD-2026-001182", "CHN-KU-2025-000078", "CHN-GU-2025-000945")
W, H = 960, 540
COLOURS = {"red": (178, 34, 34), "white": (225, 225, 220), "silver": (170, 172, 176), "grey": (120, 122, 126),
           "black": (30, 30, 32), "blue": (40, 70, 150), "green": (40, 110, 60)}
KIND_BY_TYPE = {"chain_snatching": "two_wheeler", "mobile_snatching": "two_wheeler", "street_robbery": "two_wheeler",
                "two_wheeler_theft": "two_wheeler", "cab_robbery": "car", "night_house_break": "house",
                "day_house_break": "house"}


def _rng(seed: int, name: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(f"{seed}:stills:{name}".encode()).digest()[:8], "big"))


def _km(a, b, c, d) -> float:
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _font(size: int):
    for name in ("DejaVuSansMono.ttf", "consola.ttf", "cour.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------- drawing ----------
def _street(d: ImageDraw.ImageDraw, r: random.Random, night: bool) -> None:
    sky = (18, 22, 34) if night else (150, 165, 178)
    d.rectangle([0, 0, W, H], fill=sky)
    x = 0
    while x < W:  # building row
        bw, bh = r.randint(90, 180), r.randint(140, 300)
        shade = r.randint(40, 70) if night else r.randint(110, 160)
        d.rectangle([x, H // 2 - bh, x + bw, H // 2 + 40], fill=(shade, shade - 4, shade - 8))
        for wy in range(H // 2 - bh + 15, H // 2 + 20, 34):  # windows
            for wx in range(x + 10, x + bw - 20, 30):
                lit = night and r.random() < 0.35
                d.rectangle([wx, wy, wx + 14, wy + 18], fill=(230, 200, 110) if lit else (shade - 20,) * 3)
        x += bw + r.randint(4, 18)
    road = (52, 54, 58) if night else (96, 98, 102)
    d.polygon([(0, H), (W, H), (W * 0.72, H // 2 + 40), (W * 0.28, H // 2 + 40)], fill=road)
    for i in range(6):  # lane dashes
        y0 = H // 2 + 60 + i * 42
        d.rectangle([W // 2 - 3 - i, y0, W // 2 + 3 + i, y0 + 18], fill=(200, 200, 190))
    for lx in (int(W * 0.18), int(W * 0.82)):  # lamps
        d.rectangle([lx - 3, H // 2 - 120, lx + 3, H // 2 + 60], fill=(30, 30, 30))
        if night:
            d.ellipse([lx - 30, H // 2 - 140, lx + 30, H // 2 - 100], fill=(255, 220, 140))


def _rider(d, x, y, helmet, stripe=None):
    d.ellipse([x - 13, y - 62, x + 13, y - 36], fill=helmet)  # helmet, no face
    if stripe:
        d.line([x, y - 62, x, y - 37], fill=stripe, width=4)
    d.rectangle([x - 12, y - 36, x + 12, y + 4], fill=(22, 22, 26))  # torso silhouette


def _two_wheeler(d, r, colour, helmet, riders, stripe=None):
    x, y = r.randint(int(W * 0.35), int(W * 0.6)), r.randint(int(H * 0.68), int(H * 0.8))
    for wx in (x - 60, x + 60):
        d.ellipse([wx - 30, y - 30, wx + 30, y + 30], fill=(15, 15, 15))
        d.ellipse([wx - 12, y - 12, wx + 12, y + 12], fill=(90, 90, 90))
    d.polygon([(x - 70, y - 20), (x + 75, y - 25), (x + 40, y - 60), (x - 30, y - 55)], fill=colour)
    for k in range(riders):
        _rider(d, x - 10 - 34 * k, y - 50, helmet, stripe)


def _car(d, r, colour):
    x, y = r.randint(int(W * 0.3), int(W * 0.55)), r.randint(int(H * 0.7), int(H * 0.8))
    d.rounded_rectangle([x - 120, y - 70, x + 120, y], radius=18, fill=colour)
    d.polygon([(x - 70, y - 70), (x + 60, y - 70), (x + 35, y - 115), (x - 45, y - 115)], fill=colour)
    d.polygon([(x - 60, y - 72), (x + 52, y - 72), (x + 30, y - 108), (x - 40, y - 108)], fill=(25, 30, 38))
    for wx in (x - 75, x + 75):
        d.ellipse([wx - 26, y - 22, wx + 26, y + 30], fill=(15, 15, 15))


def _house_break(d, r):
    gx, gy = r.randint(int(W * 0.2), int(W * 0.5)), int(H * 0.38)
    d.rectangle([gx, gy, gx + 150, gy + 120], fill=(70, 66, 60))
    for i in range(7):  # window grille, one bar bent
        bx = gx + 12 + i * 20
        if i == 3:
            d.line([bx, gy + 10, bx + 14, gy + 110], fill=(140, 140, 140), width=4)
        else:
            d.line([bx, gy + 10, bx, gy + 110], fill=(140, 140, 140), width=4)
    for k in range(2):  # two dark figures
        fx = gx + 190 + k * 50
        d.ellipse([fx - 12, gy + 40, fx + 12, gy + 64], fill=(18, 18, 20))
        d.rectangle([fx - 14, gy + 64, fx + 14, gy + 150], fill=(18, 18, 20))


def render(seed: int, name: str, kind: str, colour: str | None, helmet: str | None, riders: int,
           captured: datetime, camera_id: str) -> bytes:
    r = _rng(seed, name)
    night = not (6 <= captured.hour < 18)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    _street(d, r, night)
    col = COLOURS.get((colour or "").lower(), (110, 112, 116))
    hcol = (20, 20, 20) if not helmet or "black" in helmet else COLOURS.get(helmet.split()[0], (60, 60, 60))
    if kind == "two_wheeler":
        stripe = next((v for k, v in COLOURS.items() if helmet and f"{k} stripe" in helmet), None)
        _two_wheeler(d, r, col, hcol, riders, stripe)
    elif kind == "car":
        _car(d, r, col)
    else:
        _house_break(d, r)
    img = img.filter(ImageFilter.GaussianBlur(1.2))  # CCTV softness
    px = img.load()
    for _ in range(W * H // 18):  # sensor noise
        x, y, n = r.randrange(W), r.randrange(H), r.randint(-28, 28)
        p = px[x, y]
        px[x, y] = tuple(max(0, min(255, c + n)) for c in p)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=(0, 0, 0))
    d.text((12, 7), f"{camera_id}   {captured.strftime('%Y-%m-%d %H:%M:%S')} IST", fill=(240, 240, 240), font=_font(20))
    d.ellipse([W - 92, 10, W - 78, 24], fill=(220, 30, 30))
    d.text((W - 70, 7), "REC", fill=(240, 240, 240), font=_font(20))
    d.text((12, H - 28), "SYNTHETIC - NEXUS DEMO", fill=(230, 230, 230), font=_font(16))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=False)
    return buf.getvalue()


# ---------- selection ----------
def plan(src: Path, seed: int) -> list[dict]:
    crimes = {}
    for line in (src / "supabase" / "crimes.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            c = json.loads(line)
            crimes[c["crime_id"]] = c
    vehicles: dict[str, list[dict]] = {}
    for line in (src / "supabase" / "crime_vehicles.jsonl").read_text(encoding="utf-8").splitlines():
        if line:
            v = json.loads(line)
            vehicles.setdefault(v["crime_id"], []).append(v)
    cams = [(row["camera_id"], float(row["lat"]), float(row["lon"]))
            for row in csv.DictReader((src / "ref" / "cctv_cameras.csv").open(encoding="utf-8"))]
    series = json.loads((src / "_truth" / "series.json").read_text(encoding="utf-8"))
    judge = [s for s in series if set(s["crime_ids"]) & set(JUDGE_IDS)]
    out = []
    for s in sorted(judge, key=lambda s: s["series_id"]):
        for cid in sorted(s["crime_ids"]):
            c = crimes.get(cid)
            if not c or c.get("lat") is None:
                continue
            r = _rng(seed, f"plan:{cid}")
            cam = min(cams, key=lambda k: _km(c["lat"], c["lon"], k[1], k[2]))
            veh = next((v for v in vehicles.get(cid, []) if v["role"] == "used_by_offender"), None)
            off = (c.get("offenders_described") or [{}])[0]
            kind = KIND_BY_TYPE.get(c.get("sub_type") or "", "two_wheeler")
            occurred = datetime.fromisoformat(c["occurred_from"])
            for n in range(r.randint(1, 3)):
                sid = uuid.uuid5(NS, f"{cid}|cctv_still|{n}")
                out.append({
                    "crime_id": cid, "series_id": s["series_id"], "uuid": str(sid), "n": n, "kind": kind,
                    "colour": (veh or {}).get("colour") or (s.get("true_mo", {}).get("vehicle") or {}).get("colour"),
                    "helmet": off.get("helmet"), "riders": int(off.get("count") or 2) if kind == "two_wheeler" else 0,
                    "captured_at": occurred + timedelta(minutes=r.randint(-3, 8), seconds=r.randint(0, 59)),
                    "camera_id": cam[0], "camera_km": round(_km(c["lat"], c["lon"], cam[1], cam[2]), 3),
                })
    return out


def build(src: Path, seed: int = 42) -> dict:
    items = plan(src, seed)
    rows = []
    for it in items:
        jpg = render(seed, it["uuid"], it["kind"], it["colour"], it["helmet"], it["riders"], it["captured_at"],
                     it["camera_id"])
        path = f"{it['crime_id']}/{it['uuid']}.jpg"
        dst = src / "evidence" / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(jpg)
        sha = hashlib.sha256(jpg).hexdigest()
        at = it["captured_at"].isoformat()
        rows.append({
            "evidence_id": f"EV-{it['uuid']}", "crime_id": it["crime_id"], "kind": "cctv_still", "storage_path": path,
            "sha256": sha, "captured_at": at, "camera_id": it["camera_id"], "uploaded_by": "seed:data.generator.stills",
            "vision": None, "custody": [{"at": at, "by": "seed:data.generator.stills", "action": "seeded",
                                         "sha256": sha, "bytes": len(jpg), "mime": "image/jpeg"}],
            "source": "sb.evidence_media", "source_row_id": f"EV-{it['uuid']}", "synthetic": True,
        })
    rows.sort(key=lambda x: x["evidence_id"])
    (src / "supabase" / "evidence_media.jsonl").write_bytes(
        ("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for x in rows) + "\n")
        .encode())
    return {"stills": len(rows), "cases": len({x["crime_id"] for x in rows}),
            "bytes": sum(x["custody"][0]["bytes"] for x in rows),
            "series": sorted({it["series_id"] for it in items})}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", default="data/generated")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print(json.dumps(build(Path(a.src), a.seed), indent=1))


if __name__ == "__main__":
    main()
