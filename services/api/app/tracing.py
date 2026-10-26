"""Trace events (spec D3.12): one JSON line per event in logs/trace-<run_id>.jsonl, echoed to stdout.

Traces are written only by code as events happen. Rule R3: never hand-write or edit one.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))

# Fields every event carries (D3.12). Missing ones are written as null so every
# line has the same shape.
EVENT_FIELDS = (
    "timestamp",
    "run_id",
    "agent_name",
    "action",
    "input_summary",
    "output_summary",
    "target_agent",
    "model",
    "routed_model",
    "receipt_id",
    "zetaris_query_ids",
    "engine",
    "confidence",
    "retry_count",
    "status",
)


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Tracer:
    """Appends trace events for one run. Thread-safe; cheap to create."""

    def __init__(self, run_id: str, logs_dir: Path, echo: bool = True) -> None:
        self.run_id = run_id
        self.path = Path(logs_dir) / f"trace-{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self._lock = threading.Lock()

    def emit(self, agent_name: str, action: str, **fields: Any) -> dict[str, Any]:
        unknown = set(fields) - set(EVENT_FIELDS) - {"extra"}
        if unknown:
            raise ValueError(f"Unknown trace fields: {sorted(unknown)}")
        event: dict[str, Any] = {k: None for k in EVENT_FIELDS}
        event.update(
            timestamp=datetime.now(IST).isoformat(timespec="seconds"),
            run_id=self.run_id,
            agent_name=agent_name,
            action=action,
            zetaris_query_ids=[],
            retry_count=0,
        )
        event.update(fields)
        line = json.dumps(event, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if self.echo:
                print(line, file=sys.stdout, flush=True)
        return event

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
