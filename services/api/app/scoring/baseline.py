"""Rules-only baseline for the evaluation (spec F3): same category, <= 2 km, <= 14 days.

`python -m app.eval` compares the agent pipeline's precision and recall against this.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .factors import days_apart, distance_km

BASELINE_MAX_KM = 2.0
BASELINE_MAX_DAYS = 14.0


def baseline_link(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> bool:
    """True when the rules-only baseline would link the two crimes."""
    if crime_a.get("crime_id") == crime_b.get("crime_id"):
        return False
    cat_a, cat_b = crime_a.get("category"), crime_b.get("category")
    if not cat_a or cat_a != cat_b:
        return False
    d, days = distance_km(crime_a, crime_b), days_apart(crime_a, crime_b)
    if d is None or days is None:
        return False
    return d <= BASELINE_MAX_KM and days <= BASELINE_MAX_DAYS


# ---------------------------------------------------------------------------
# Stronger baseline: rules + vehicle/plate (engg/docs/eval/STRONGER_BASELINE_PREREG.md, fixed before the run)
# ---------------------------------------------------------------------------

PLATE_FRAGMENT_MIN_KNOWN = 4  # agreeing known characters, right-aligned, none conflicting (e.g. "4471")


def _plate_fragment_match(a: Any, b: Any) -> bool | None:
    """True / False when both plates are present; None when either is missing (prereg item 2)."""
    from .factors import normalise_plate

    pa, pb = normalise_plate(a), normalise_plate(b)
    if not pa or not pb:
        return None
    n = max(len(pa), len(pb))
    pa, pb = pa.rjust(n, "?"), pb.rjust(n, "?")
    known = 0
    for ca, cb in zip(pa, pb):
        if ca == "?" or cb == "?":
            continue
        if ca != cb:
            return False
        known += 1
    return known >= PLATE_FRAGMENT_MIN_KNOWN


def _same(x: Any, y: Any) -> bool:
    return bool(x) and bool(y) and str(x).strip().lower() == str(y).strip().lower()


def vehicle_match(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> bool:
    """Offender vehicles match: compatible plates (>= 4 known characters agree, none conflict) when both plates are
    present; otherwise the same vehicle type and colour. Conflicting plates never match."""
    def offender(c: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return [v for v in c.get("vehicles") or [] if isinstance(v, Mapping)
                and v.get("role", "used_by_offender") == "used_by_offender"]

    for va in offender(crime_a):
        for vb in offender(crime_b):
            plates = _plate_fragment_match(va.get("plate"), vb.get("plate"))
            if plates is not None:
                if plates:
                    return True
                continue
            if _same(va.get("type"), vb.get("type")) and _same(va.get("colour"), vb.get("colour")):
                return True
    return False


def _same_category(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> bool:
    cat_a = crime_a.get("category")
    return crime_a.get("crime_id") != crime_b.get("crime_id") and bool(cat_a) and cat_a == crime_b.get("category")


def rules_plus_vehicle_link(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> bool:
    """PRIMARY stronger baseline: same category AND (rules-only window OR vehicle match)."""
    if not _same_category(crime_a, crime_b):
        return False
    return baseline_link(crime_a, crime_b) or vehicle_match(crime_a, crime_b)


def rules_and_vehicle_link(crime_a: Mapping[str, Any], crime_b: Mapping[str, Any]) -> bool:
    """SECONDARY (strict): the rules-only window AND a vehicle match."""
    return baseline_link(crime_a, crime_b) and vehicle_match(crime_a, crime_b)
