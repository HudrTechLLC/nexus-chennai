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
