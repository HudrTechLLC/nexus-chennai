"""D3.6 public tip (+ media, messages) and D3.13 public incident.

Tips carry no IP, user agent, cookie, device id, exact time or contact detail (spec J1):
`received_week` replaces the time and `approx_cell` (H3 r8) replaces the location.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from .common import NexusModel

_ISO_WEEK = re.compile(r"^\d{4}-W(0[1-9]|[1-4]\d|5[0-3])$")


def _iso_week(v: str) -> str:
    if not _ISO_WEEK.match(v):
        raise ValueError("expected an ISO week like 2026-W43")
    return v


class TipMedia(NexusModel):
    kind: Literal["image", "video", "audio"]
    path: str
    exif_stripped: bool
    faces_blurred: bool


class TipGuard(NexusModel):
    verdict: Literal["clean", "quarantine", "urgent"]
    injection: bool
    spam_score: float = Field(ge=0, le=1)
    threat: bool


class Tip(NexusModel):
    tip_id: str
    public_incident_id: str | None = None
    channel: Literal["web", "voice", "whatsapp"]
    category: str
    text: str
    media: list[TipMedia] = []
    follow_up_enabled: bool = False
    tip_code_hash: str | None = None
    guard: TipGuard | None = None  # None until Tip Guard has screened it
    approx_cell: str | None = None
    received_week: str
    synthetic: bool

    _week = field_validator("received_week")(classmethod(lambda cls, v: _iso_week(v)))


class TipMessage(NexusModel):
    """tip_messages row. Part I calls the column `from`; it is `sender` because `from` is reserved."""

    tip_id: str
    sender: Literal["police", "tipster"]
    text: str
    at: AwareDatetime


class PublicImage(NexusModel):
    path: str
    blurred: bool


class PublicIncident(NexusModel):
    """What the public portal shows. Never carries crime_id, station or exact place."""

    public_incident_id: str
    title: str
    category: str
    area_label: str
    cell: str
    week: str
    time_window: str
    summary: str
    looking_for: list[str] = []
    images: list[PublicImage] = []
    approved_by: str
    sanitiser_model: str
    published_at: AwareDatetime | None = None

    _week = field_validator("week")(classmethod(lambda cls, v: _iso_week(v)))
