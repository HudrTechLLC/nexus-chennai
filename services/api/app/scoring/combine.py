"""Combine factor values into one pair score (spec F1 steps 4-8, F2). Pure code (rule R7).

Order of operations, fixed and tested:

1. Base score = sum(w_i * v_i) / sum(w_i) over factors that had data (value not None).
   A factor the Skeptic struck keeps its weight in the denominator with value 0, so a
   strike can never raise the score (D3.12 shows a strike moving 0.86 -> 0.82).
2. Add the H-MEM adjustments; their SUM is capped at +/-0.08 (F1 step 7).
3. Apply the forensic floor: an unstruck forensic match sets the score to at least 0.8
   and always raises an alert (F2). It runs after memory, so memory cannot push a
   forensic pair below the alert line.
4. Clamp to [0, 1], round to 4 dp, then band.
5. Evidence-coverage guard (D-016): coverage = sum of default-or-given weights of
   unstruck factors with data. Coverage < 0.50 caps the band at "medium"; fewer than
   2 such factors means no alert. A forensic match is exempt: F2 says it always alerts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .weights import (
    BAND_HIGH,
    BAND_MEDIUM,
    DEFAULT_WEIGHTS,
    FACTORS,
    FORENSIC_FLOOR,
    HMEM_CAP,
    MIN_COVERAGE_FOR_HIGH,
    MIN_FACTORS_FOR_ALERT,
    SCORE_DECIMALS,
    WEIGHTS_VERSION,
)


@dataclass
class FactorResult:
    """One factor of a pair, shaped like a D3.11 `factors[]` entry.

    `reason` is left empty here: the Linker's reason lane writes it from the rows,
    and can never change `value` (rule R7).
    """

    factor: str
    value: float | None
    weight: float = 0.0
    evidence: list[dict[str, Any]] = field(default_factory=list)
    struck_by_skeptic: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PairScore:
    score: float | None
    band: str | None
    alert: bool
    base_score: float | None
    memory_delta: float
    memory_applied: list[dict[str, Any]]
    forensic_floor_applied: bool
    factors: list[FactorResult]
    weights_version: str
    coverage: float = 0.0
    factors_with_data: int = 0
    coverage_capped: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["factors"] = [f.to_dict() for f in self.factors]
        return d


def band_for(score: float | None) -> str | None:
    """'high' >= 0.75, 'medium' >= 0.55, otherwise None (no alert)."""
    if score is None:
        return None
    s = round(score, SCORE_DECIMALS)
    if s >= BAND_HIGH:
        return "high"
    if s >= BAND_MEDIUM:
        return "medium"
    return None


def cap_memory(adjustments: Sequence[Mapping[str, Any]] | None) -> tuple[float, list[dict[str, Any]]]:
    """Sum H-MEM adjustments (`hmem.adjust` results) and cap the total at +/-HMEM_CAP.

    Returns the capped delta and the `memory_applied` entries the alert card shows.
    """
    total = 0.0
    applied: list[dict[str, Any]] = []
    for adj in adjustments or []:
        delta = float(adj.get("delta") or 0.0)
        if delta == 0.0:
            continue
        total += delta
        ids = list(adj.get("memory_ids") or [])
        applied.append(
            {
                "memory_id": ids[0] if ids else None,
                "memory_ids": ids,
                "effect": f"{delta:+.2f}",
                "text": adj.get("reason") or "",
            }
        )
    capped = max(-HMEM_CAP, min(HMEM_CAP, total))
    return round(capped, SCORE_DECIMALS), applied


def score_pair(
    factors: Sequence[FactorResult],
    memory: Sequence[Mapping[str, Any]] | None = None,
    weights: Mapping[str, float] | None = None,
    weights_version: str | None = None,
) -> PairScore:
    """Combine factor results into a scored, banded pair.

    `weights` defaults to the F2 defaults. Unknown factor names are rejected so a typo
    can't silently drop a factor.
    """
    w = dict(weights if weights is not None else DEFAULT_WEIGHTS)
    version = weights_version or (WEIGHTS_VERSION if weights is None else "custom")
    out: list[FactorResult] = []
    num = den = coverage = 0.0
    with_data = 0
    for f in factors:
        if f.factor not in FACTORS:
            raise ValueError(f"Unknown factor '{f.factor}'")
        weight = float(w.get(f.factor, 0.0))
        fr = FactorResult(
            factor=f.factor,
            value=None if f.value is None else max(0.0, min(1.0, float(f.value))),
            weight=weight,
            evidence=list(f.evidence),
            struck_by_skeptic=f.struck_by_skeptic,
            reason=f.reason,
        )
        out.append(fr)
        if fr.struck_by_skeptic:
            den += weight  # counts as 0 with its full weight: a strike only ever lowers the score
        elif fr.value is not None:
            num += weight * fr.value
            den += weight
            coverage += weight
            with_data += 1

    if den <= 0.0:
        return PairScore(None, None, False, None, 0.0, [], False, out, version)

    base = num / den
    delta, applied = cap_memory(memory)
    score = base + delta

    forensic_hit = any(
        f.factor == "forensic" and not f.struck_by_skeptic and (f.value or 0.0) >= 1.0 for f in out
    )
    floor_applied = forensic_hit and score < FORENSIC_FLOOR
    if forensic_hit:
        score = max(score, FORENSIC_FLOOR)

    score = round(max(0.0, min(1.0, score)), SCORE_DECIMALS)
    band = band_for(score)
    coverage = round(coverage, SCORE_DECIMALS)
    capped = False
    if not forensic_hit:
        if band == "high" and coverage < MIN_COVERAGE_FOR_HIGH:
            band, capped = "medium", True
        if with_data < MIN_FACTORS_FOR_ALERT and band is not None:
            band, capped = None, True
    alert = forensic_hit or band is not None
    return PairScore(
        score=score,
        band=band,
        alert=alert,
        base_score=round(base, SCORE_DECIMALS),
        memory_delta=delta,
        memory_applied=applied,
        forensic_floor_applied=floor_applied,
        factors=out,
        weights_version=version,
        coverage=coverage,
        factors_with_data=with_data,
        coverage_capped=capped,
    )


def strike(pair: PairScore, factor: str, memory: Sequence[Mapping[str, Any]] | None = None,
           weights: Mapping[str, float] | None = None) -> PairScore:
    """Skeptic helper: mark one factor struck and recompute the whole score."""
    factors = [
        FactorResult(f.factor, f.value, f.weight, f.evidence, f.struck_by_skeptic or f.factor == factor, f.reason)
        for f in pair.factors
    ]
    return score_pair(factors, memory, weights, None if weights is None else pair.weights_version)
