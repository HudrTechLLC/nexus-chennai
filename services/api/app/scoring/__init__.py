"""Link scoring (spec Part F2). Numbers are computed here, in code; models only explain (rule R7).

This package must never import a model or data adapter; a test enforces it.
"""

from . import factors
from .baseline import baseline_link
from .combine import FactorResult, PairScore, band_for, cap_memory, score_pair, strike
from .weights import (
    ALERT_THRESHOLD,
    BAND_HIGH,
    BAND_MEDIUM,
    DEFAULT_WEIGHTS,
    FACTORS,
    FORENSIC_FLOOR,
    HMEM_CAP,
    WEIGHTS_VERSION,
)

__all__ = [
    "ALERT_THRESHOLD",
    "BAND_HIGH",
    "BAND_MEDIUM",
    "DEFAULT_WEIGHTS",
    "FACTORS",
    "FORENSIC_FLOOR",
    "HMEM_CAP",
    "WEIGHTS_VERSION",
    "FactorResult",
    "PairScore",
    "band_for",
    "baseline_link",
    "cap_memory",
    "factors",
    "score_pair",
    "strike",
]
