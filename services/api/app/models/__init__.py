"""Domain models for spec D3 (canonical data formats).

One Pydantic v2 model per D3 section. Field names match the spec exactly; unknown fields
are rejected (`extra="forbid"`) so a typo in the generator or an agent fails loudly.
Other lanes import from here: `from app.models import Crime, LinkAlert, ...`.
"""

from .common import NexusModel
from .crime import (
    Crime,
    CrimeFeatures,
    CrimeLocation,
    Entities,
    LegacyCctnsRow,
    MO,
    OffenderDescription,
    PropertyItem,
    Section,
    Vehicle,
    Victim,
)
from .evidence import Custody, EvidenceMedia, Vision, WitnessStatement
from .feeds import AnprRead, CallLocation, CallLog, CctvCamera, HistorySheet, NewsArticle, Release
from .alerts import (
    FACTOR_WEIGHTS,
    REJECTION_REASONS,
    AlertDecision,
    Decision,
    EvidenceRef,
    LinkAlert,
    LinkFactor,
    MemoryApplied,
    SkepticReview,
    band_for,
)
from .public import PublicImage, PublicIncident, Tip, TipGuard, TipMedia, TipMessage
from .trace import TraceEvent

__all__ = [
    "AlertDecision",
    "AnprRead",
    "CallLocation",
    "CallLog",
    "CctvCamera",
    "Crime",
    "CrimeFeatures",
    "CrimeLocation",
    "Custody",
    "Decision",
    "Entities",
    "EvidenceMedia",
    "EvidenceRef",
    "FACTOR_WEIGHTS",
    "HistorySheet",
    "LegacyCctnsRow",
    "LinkAlert",
    "LinkFactor",
    "MO",
    "MemoryApplied",
    "NewsArticle",
    "NexusModel",
    "OffenderDescription",
    "PropertyItem",
    "PublicImage",
    "PublicIncident",
    "REJECTION_REASONS",
    "Release",
    "Section",
    "SkepticReview",
    "Tip",
    "TipGuard",
    "TipMedia",
    "TipMessage",
    "TraceEvent",
    "Vehicle",
    "Victim",
    "Vision",
    "WitnessStatement",
    "band_for",
]
