"""D3.7 news, D3.8 112 call log, D3.9 ANPR read, D3.10 CCTV camera / release / history sheet.

The CSV/Parquet records (D3.9, D3.10) use the spec's column names as fields.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from .common import NexusModel


def _split_tags(v: object) -> object:
    """CSV stores tag lists as "a;b;c"."""
    if isinstance(v, str):
        return [t.strip() for t in v.split(";") if t.strip()]
    return v


class NewsArticle(NexusModel):
    article_id: str
    outlet: str
    published_at: AwareDatetime
    headline: str
    body: str
    places_mentioned: list[str] = []
    url: str
    synthetic: bool


class CallLocation(NexusModel):
    lat: float
    lon: float


class CallLog(NexusModel):
    call_id: str
    received_at: AwareDatetime
    caller: Literal["masked"] = "masked"
    category: str
    location: CallLocation
    cell: str
    dispatched_unit: str | None = None
    outcome: str
    fir_ref: str | None = None
    synthetic: bool


class AnprRead(NexusModel):
    read_id: str
    camera_id: str
    read_at: AwareDatetime
    plate_text: str
    plate_confidence: float = Field(ge=0, le=1)
    direction: Literal["N", "S", "E", "W", "NE", "NW", "SE", "SW"]
    lat: float
    lon: float
    h3_r9: str


class CctvCamera(NexusModel):
    camera_id: str
    owner_type: str  # police, private_shop, community, ...
    owner_name: str
    lat: float
    lon: float
    heading_deg: float = Field(ge=0, lt=360)
    fov_deg: float = Field(gt=0, le=360)
    range_m: float = Field(gt=0)
    retention_days: int = Field(ge=0)
    contact_station: str


class Release(NexusModel):
    release_id: str
    person_ref: str
    released_on: date
    release_type: Literal["bail", "sentence_complete", "parole", "acquitted"]
    prior_mo_tags: list[str] = []
    residence_ward: int | None = None
    station_of_residence: str | None = None

    _split = field_validator("prior_mo_tags", mode="before")(_split_tags)


class HistorySheet(NexusModel):
    """D3.10 names this file but gives no columns; this minimal set is nexus-1's choice."""

    sheet_id: str
    person_ref: str
    station_id: str
    opened_on: date
    category: str  # e.g. rowdy, property_offender
    mo_tags: list[str] = []
    residence_ward: int | None = None
    active: bool = True

    _split = field_validator("mo_tags", mode="before")(_split_tags)
