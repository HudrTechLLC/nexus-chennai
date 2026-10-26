"""D3.1 Crime, D3.2 extracted MO features, D3.3 legacy CCTNS CSV row."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import NexusModel

CRIME_STATUSES = ("registered", "under_investigation", "charge_sheeted", "undetected", "closed", "transferred")
CrimeStatus = Literal["registered", "under_investigation", "charge_sheeted", "undetected", "closed", "transferred"]


# ---------- D3.1 Crime ----------
class Section(NexusModel):
    code: str
    ipc_equiv: str | None = None


class CrimeLocation(NexusModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    address: str | None = None
    ward: int | None = None
    h3_r9: str | None = None
    geohash7: str | None = None


class PropertyItem(NexusModel):
    type: str
    weight_g: float | None = None
    value_inr: int | None = None


class Vehicle(NexusModel):
    role: str  # e.g. used_by_offender, stolen, victim_vehicle
    type: str
    make_model: str | None = None
    colour: str | None = None
    plate: str | None = None  # may be partial: "TN 09 ?? 4471"


class OffenderDescription(NexusModel):
    count: int | None = None
    helmet: str | None = None
    build: str | None = None
    age_band: str | None = None


class Victim(NexusModel):
    gender: str | None = None
    age_band: str | None = None


class Crime(NexusModel):
    """Canonical crime, as exposed by the Zetaris view v_crime_unified."""

    crime_id: str
    source: str
    source_row_id: str
    station_id: str
    fir_no: str
    category: str
    sub_type: str | None = None
    sections: list[Section] = []
    occurred_from: AwareDatetime
    occurred_to: AwareDatetime | None = None
    reported_at: AwareDatetime
    location: CrimeLocation
    severity: int = Field(ge=1, le=5)
    property: list[PropertyItem] = []
    weapon: str | None = None
    vehicles: list[Vehicle] = []
    offenders_described: list[OffenderDescription] = []
    victims: list[Victim] = []
    status: CrimeStatus
    synthetic: bool
    # Part I stores the FIR narrative on crimes; D3.1 omits it from the example.
    narrative: str | None = None


# ---------- D3.2 Extracted MO features ----------
class MO(NexusModel):
    approach: str | None = None
    offender_count: int | None = None
    target: str | None = None
    target_item: str | None = None
    escape: str | None = None
    violence: str | None = None
    time_band: str | None = None
    place_type: list[str] = []
    disguise: list[str] = []
    verbal: str | None = None


class Entities(NexusModel):
    plates: list[str] = []
    persons: list[str] = []
    phones: list[str] = []


class CrimeFeatures(NexusModel):
    """Written by the Extractor into crime_features."""

    crime_id: str
    extractor_version: str
    model: str
    receipt_id: str | None = None
    mo: MO
    visual_tags: list[str] = []
    entities: Entities = Entities()
    confidence: float = Field(ge=0, le=1)
    reviewed_by_officer: bool = False


# ---------- D3.3 Legacy CCTNS-style CSV ----------
class LegacyCctnsRow(NexusModel):
    """One raw row of legacy/cctns_*.csv. Column names are the CSV headers, verbatim.

    Values stay raw on purpose (DD-MM-YYYY dates, IPC sections, upper case); the
    Zetaris semantic layer normalises them in v_crime_unified.
    """

    PS_CODE: str
    FIR_NUM: str
    FIR_DT: str
    OCC_DT_FROM: str
    OCC_DT_TO: str | None = None
    ACT_SEC: str
    MAJOR_HEAD: str
    MINOR_HEAD: str | None = None
    PLACE_OCC: str | None = None
    LAT: float | None = None
    LONG: float | None = None
    BRIEF_FACTS: str | None = None
    PROP_STOLEN_RS: int | None = None
    IO_NAME: str | None = None
