"""Supabase-backed store for the agents (spec C1 rule 2: writes go to the system of record).

- `runs` row first (link_alerts.run_id references it), finished at the end.
- `crime_features`: upsert on crime_id, D3.2 columns only.
- `link_alerts` + `link_factors`: upsert. `status` is never written by the agents, so a
  re-run cannot undo an analyst's decision; new rows default to 'pending'.
- `notifications`: one per police user of each station involved, plus analysts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..adapters.supabase import SupabaseClient
from ..tracing import IST, Tracer

FEATURE_COLUMNS = ("crime_id", "extractor_version", "mo", "visual_tags", "entities", "model", "receipt_id",
                   "confidence", "synthetic")
ALERT_COLUMNS = ("alert_id", "kind", "crimes", "stations", "score", "band", "coverage", "memory_applied", "skeptic",
                 "rationale", "recommended_action", "run_id", "synthetic")
FACTOR_COLUMNS = ("factor", "weight", "value", "evidence", "reason", "struck_by_skeptic")
RUN_STATUS = {"success": "success"}  # anything else (partial, deadline, error) is recorded as failed


class SupabaseStore:
    def __init__(self, client: SupabaseClient, tracer: Tracer) -> None:
        self.client = client
        self.tracer = tracer

    # ----- runs ----------------------------------------------------------------

    def start_run(self, run_id: str, kind: str, log_path: str) -> None:
        self.client.upsert("runs", {"run_id": run_id, "kind": kind, "status": "running", "log_path": log_path},
                           on_conflict="run_id")

    def finish_run(self, run_id: str, status: str) -> None:
        self.client.update("runs", {"run_id": f"eq.{run_id}"},
                           {"status": RUN_STATUS.get(status, "failed"),
                            "finished": datetime.now(IST).isoformat(timespec="seconds")})

    # ----- Store protocol ---------------------------------------------------------

    def upsert_features(self, features: dict[str, Any]) -> None:
        row = {k: features.get(k) for k in FEATURE_COLUMNS}
        self.client.upsert("crime_features", row, on_conflict="crime_id")

    def write_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        row = {k: alert.get(k) for k in ALERT_COLUMNS}
        self.client.upsert("link_alerts", row, on_conflict="alert_id")
        factors = [{"alert_id": alert["alert_id"], **{k: f.get(k) for k in FACTOR_COLUMNS}}
                   for f in alert.get("factors") or []]
        if factors:
            self.client.upsert("link_factors", factors, on_conflict="alert_id,factor")
        return alert

    def notify(self, notifications: list[dict[str, Any]]) -> None:
        stations = sorted({n["station_id"] for n in notifications if n.get("station_id")})
        if not notifications:
            return
        users = self.client.select("profiles", {"select": "user_id,role,station_id",
                                                "or": f"(station_id.in.({','.join(stations)}),role.eq.analyst)"})
        rows = []
        first = notifications[0]
        for u in users:
            rows.append({"user_id": u["user_id"], "kind": first["kind"], "title": first["title"],
                         "body": first.get("body"), "link": first.get("link")})
        if rows:
            self.client.insert("notifications", rows)
        self.tracer.emit("Alert writer", "notify", input_summary=first.get("link"),
                         output_summary=f"{len(rows)} users across {len(stations)} stations", status="ok")
