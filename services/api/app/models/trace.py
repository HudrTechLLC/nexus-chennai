"""D3.12 trace event. Its fields are exactly app.tracing.EVENT_FIELDS (a test checks this)."""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field

from .common import NexusModel


class TraceEvent(NexusModel):
    timestamp: AwareDatetime
    run_id: str
    agent_name: str
    action: str
    input_summary: str | None = None
    output_summary: str | None = None
    target_agent: str | None = None
    model: str | None = None
    routed_model: str | None = None
    receipt_id: str | None = None
    zetaris_query_ids: list[str] | None = None
    engine: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    retry_count: int | None = None
    status: str | None = None
    extra: dict[str, Any] | None = None
