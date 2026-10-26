"""D3.11 link alert and its factors; F4 rejection reasons. F2 weights/bands come from app.scoring."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from ..scoring import DEFAULT_WEIGHTS, band_for  # noqa: F401  (re-exported)
from .common import NexusModel

# F2 weights and bands live in app.scoring (nexus-3); re-exported here, never duplicated.
FACTOR_WEIGHTS = DEFAULT_WEIGHTS

# F4 fixed list (plus free text in `note`).
REJECTION_REASONS = (
    "different_offenders",
    "coincidental_location",
    "already_linked",
    "data_error",
    "insufficient_evidence",
    "different_mo",
    "duplicate_fir",
    "other",
)
ReasonCode = Literal[
    "different_offenders",
    "coincidental_location",
    "already_linked",
    "data_error",
    "insufficient_evidence",
    "different_mo",
    "duplicate_fir",
    "other",
]

Band = Literal["high", "medium"]


class EvidenceRef(NexusModel):
    view: str  # Zetaris view the row came from, e.g. v_crime_features
    row: str  # source row id


class LinkFactor(NexusModel):
    factor: str
    weight: float = Field(ge=0, le=1)
    value: float = Field(ge=0, le=1)
    evidence: list[EvidenceRef] = []
    reason: str
    struck_by_skeptic: bool = False

    @field_validator("factor")
    @classmethod
    def _known_factor(cls, v: str) -> str:
        if v not in FACTOR_WEIGHTS:
            raise ValueError(f"unknown factor '{v}'; F2 factors are {sorted(FACTOR_WEIGHTS)}")
        return v


class MemoryApplied(NexusModel):
    memory_id: str
    effect: str  # signed delta as shown on the card, e.g. "+0.03"
    text: str


class SkepticReview(NexusModel):
    rounds: int = Field(ge=0)
    struck: list[str] = []
    verdict: str  # e.g. approved, needs_revision, rejected


class Decision(NexusModel):
    by: str
    at: AwareDatetime
    reason_code: ReasonCode | None = None
    note: str | None = None


class LinkAlert(NexusModel):
    alert_id: str
    kind: Literal["pair", "series", "hotspot"]
    crimes: list[str] = Field(min_length=1)
    stations: list[str] = []
    score: float = Field(ge=0, le=1)
    band: Band
    factors: list[LinkFactor] = []
    memory_applied: list[MemoryApplied] = []
    skeptic: SkepticReview | None = None
    rationale: str
    recommended_action: str | None = None
    status: Literal["pending", "approved", "rejected"] = "pending"
    decision: Decision | None = None
    run_id: str
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _decision_matches_status(self) -> LinkAlert:
        if self.status == "pending" and self.decision is not None:
            raise ValueError("a pending alert cannot carry a decision")
        if self.status == "rejected" and (self.decision is None or self.decision.reason_code is None):
            raise ValueError("a rejected alert needs a decision with a reason_code (F4)")
        return self


class AlertDecision(NexusModel):
    """A row of alert_decisions: what the console writes when an analyst decides."""

    alert_id: str
    decision: Literal["approve", "reject"]
    reason_code: ReasonCode | None = None
    note: str | None = None
    by: str
    at: AwareDatetime

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> AlertDecision:
        if self.decision == "reject" and self.reason_code is None:
            raise ValueError("reject needs a reason_code (F4)")
        return self
