"""Geo helpers shared by the reference build and the generator.

Every row carries precomputed cells (spec E5) so Zetaris can join spatially by equality:
h3_r9 (internal), h3_r8 (public / tips) and geohash7 (geohash5 = first 5 characters).
"""

from __future__ import annotations

import h3

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat: float, lon: float, precision: int = 7) -> str:
    lat_lo, lat_hi, lon_lo, lon_hi = -90.0, 90.0, -180.0, 180.0
    out, bits, ch, even = [], 0, 0, True
    while len(out) < precision:
        if even:
            mid = (lon_lo + lon_hi) / 2
            if lon >= mid:
                ch, lon_lo = (ch << 1) | 1, mid
            else:
                ch, lon_hi = ch << 1, mid
        else:
            mid = (lat_lo + lat_hi) / 2
            if lat >= mid:
                ch, lat_lo = (ch << 1) | 1, mid
            else:
                ch, lat_hi = ch << 1, mid
        even = not even
        bits += 1
        if bits == 5:
            out.append(_BASE32[ch])
            bits, ch = 0, 0
    return "".join(out)


def cells(lat: float, lon: float) -> dict[str, str]:
    """All precomputed cells for one point."""
    return {
        "h3_r9": h3.latlng_to_cell(lat, lon, 9),
        "h3_r8": h3.latlng_to_cell(lat, lon, 8),
        "geohash7": geohash(lat, lon, 7),
    }


def geohash_bbox(gh: str) -> tuple[float, float, float, float]:
    """(lat_lo, lat_hi, lon_lo, lon_hi) of a geohash cell."""
    lat_lo, lat_hi, lon_lo, lon_hi = -90.0, 90.0, -180.0, 180.0
    even = True
    for c in gh:
        v = _BASE32.index(c)
        for bit in (16, 8, 4, 2, 1):
            if even:
                mid = (lon_lo + lon_hi) / 2
                if v & bit:
                    lon_lo = mid
                else:
                    lon_hi = mid
            else:
                mid = (lat_lo + lat_hi) / 2
                if v & bit:
                    lat_lo = mid
                else:
                    lat_hi = mid
            even = not even
    return lat_lo, lat_hi, lon_lo, lon_hi


def geohash_neighbours4(gh: str) -> dict[str, str]:
    """The N, S, E, W neighbours of a cell (what v_link_candidates blocks on: gh5_n/s/e/w)."""
    lat_lo, lat_hi, lon_lo, lon_hi = geohash_bbox(gh)
    clat, clon = (lat_lo + lat_hi) / 2, (lon_lo + lon_hi) / 2
    dlat, dlon = lat_hi - lat_lo, lon_hi - lon_lo
    p = len(gh)
    return {"n": geohash(clat + dlat, clon, p), "s": geohash(clat - dlat, clon, p),
            "e": geohash(clat, clon + dlon, p), "w": geohash(clat, clon - dlon, p)}


def gh5_block(a: str, b: str) -> bool:
    """True when b's geohash5 is a's own cell or one of its 4 neighbours (spec E5 blocking)."""
    a5, b5 = a[:5], b[:5]
    return a5 == b5 or b5 in geohash_neighbours4(a5).values()


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def offset(lat: float, lon: float, dist_km: float, bearing_deg: float) -> tuple[float, float]:
    """Point at a distance and bearing (small-distance approximation, fine below ~50 km)."""
    import math

    b = math.radians(bearing_deg)
    dlat = (dist_km * math.cos(b)) / 111.32
    dlon = (dist_km * math.sin(b)) / (111.32 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon
