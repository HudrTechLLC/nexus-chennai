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
