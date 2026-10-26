"""D3.4 evidence media metadata, D3.5 witness statement."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import NexusModel


class Vision(NexusModel):
    model: str
    tags: list[str] = []
    plate_read: str | None = None
    plate_confidence: float | None = Field(default=None, ge=0, le=1)


class Custody(NexusModel):
    at: AwareDatetime
    by: str
    action: str


class EvidenceMedia(NexusModel):
    evidence_id: str
    crime_id: str
    kind: Literal["cctv_still", "cctv_clip", "photo", "scan", "audio", "document"]
    storage_path: str
    sha256: str
    captured_at: AwareDatetime | None = None
    camera_id: str | None = None
    uploaded_by: str
    vision: Vision | None = None
    custody: list[Custody] = []
    synthetic: bool


class WitnessStatement(NexusModel):
    statement_id: str
    crime_id: str
    witness_ref: str  # always masked, e.g. "W-2 (masked)"
    mode: Literal["text", "audio"]
    audio_path: str | None = None
    text: str | None = None
    transcript_model: str | None = None
    recorded_at: AwareDatetime
    synthetic: bool
