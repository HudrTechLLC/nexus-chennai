"""F2 default factor weights, bands and caps (spec Part F2, F1 step 7).

These are the defaults. Admins may pass edited weights to the scoring functions, but
the defaults here change only with a recorded decision (rule R12).
"""

from __future__ import annotations

from types import MappingProxyType

WEIGHTS_VERSION = "f2-default-v1"

# Order follows the F2 table.
DEFAULT_WEIGHTS: MappingProxyType[str, float] = MappingProxyType(
    {
        "mo_similarity": 0.25,
        "space_time": 0.15,
        "vehicle": 0.15,
        "suspect_description": 0.12,
        "weapon_tool": 0.08,
        "target_profile": 0.05,
        "forensic": 0.08,
        "corroboration": 0.07,
        "offender_return": 0.05,
    }
)

FACTORS: tuple[str, ...] = tuple(DEFAULT_WEIGHTS)

# Bands (F2): high >= 0.75, medium 0.55-0.75, below 0.55 no alert.
BAND_HIGH = 0.75
BAND_MEDIUM = 0.55
ALERT_THRESHOLD = BAND_MEDIUM

# A forensic match sets a floor on the final score and always raises an alert (F2).
FORENSIC_FLOOR = 0.8

# H-MEM adjustments are bounded: max +/-0.08 in total per pair (F1 step 7).
HMEM_CAP = 0.08

# Evidence-coverage guard (DECISIONS D-016): coverage = sum of the weights of unstruck
# factors that had data. Below MIN_COVERAGE_FOR_HIGH the band is capped at "medium";
# with fewer than MIN_FACTORS_FOR_ALERT factors with data there is no alert
# (a forensic match still always alerts, per F2).
MIN_COVERAGE_FOR_HIGH = 0.50
MIN_FACTORS_FOR_ALERT = 2

# Scores are rounded before banding so 0.5499999999 and 0.55 band the same way.
SCORE_DECIMALS = 4
