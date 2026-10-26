"""Shared base for every D3 model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NexusModel(BaseModel):
    """Strict base: unknown fields are an error, values are validated on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
