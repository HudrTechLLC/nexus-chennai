"""Supabase-backed store for the agents (spec C1 rule 2: writes go to the system of record).

- `runs` row first (link_alerts.run_id references it), finished at the end.
- `crime_features`: upsert on crime_id, D3.2 columns only.
- `link_alerts` + `link_factors`: upsert. `status` is never written by the agents, so a
  re-run cannot undo an analyst's decision; new rows default to 'pending'.
- `notifications`: one per police user of each station involved, plus analysts.
- `series` + `series_members`: from `detect_series` (never from _truth). The id stays stable as a
  series grows (reuse of the stored series sharing most members). `status` is never written, so an
  analyst's confirm/close survives re-runs; `dossier` is written only by `write_dossier`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..adapters.supabase import SupabaseClient
from ..agents.base import ExcludeFn, NameFn, choose_series_id, series_name
from ..tracing import IST, Tracer
from .redact import redact_event

FEATURE_COLUMNS = ("crime_id", "extractor_version", "mo", "visual_tags", "entities", "model", "receipt_id",
                   "confidence", "synthetic")
ALERT_COLUMNS = ("alert_id", "kind", "crimes", "stations", "score", "band", "coverage", "memory_applied", "skeptic",
                 "rationale", "recommended_action", "run_id", "synthetic", "weights_version")
FACTOR_COLUMNS = ("factor", "weight", "value", "evidence", "reason", "struck_by_skeptic")
TRACE_COLUMNS = ("input_summary", "output_summary", "target_agent", "model", "routed_model", "receipt_id",
                 "engine", "confidence", "retry_count", "status", "extra")
TRACE_BATCH = 500
RUN_STATUS = {"success": "success"}  # anything else (partial, deadline, error) is recorded as failed


def trace_row(run_id: str, seq: int, event: dict[str, Any]) -> dict[str, Any]:
    e = redact_event(event)
    return {"run_id": run_id, "seq": seq, "ts": e.get("timestamp"), "agent_name": e.get("agent_name") or "?",
            "action": e.get("action") or "?", "zetaris_query_ids": list(e.get("zetaris_query_ids") or []),
            **{k: e.get(k) for k in TRACE_COLUMNS}}


class SupabaseStore:
    def __init__(self, client: SupabaseClient, tracer: Tracer) -> None:
        self.client = client
        self.tracer = tracer
        self.removed: list[dict[str, Any]] = []  # series_member_removed rows (D-033); the runner traces them

    # ----- runs ----------------------------------------------------------------

    def start_run(self, run_id: str, kind: str, log_path: str, subject: str | None = None) -> None:
        """`subject` (0006_03): the crime a case run is about, so the console can find its trace."""
        row = {"run_id": run_id, "kind": kind, "status": "running", "log_path": log_path}
        if subject:
            try:
                self.client.upsert("runs", {**row, "subject": subject}, on_conflict="run_id")
                return
            except Exception as exc:  # 0006_03 not applied yet: the run still starts, without a subject
                if "subject" not in str(exc):
                    raise
        self.client.upsert("runs", row, on_conflict="run_id")

    def finish_run(self, run_id: str, status: str, kind: str = "case") -> None:
        """Close the run row, then copy its (redacted) trace lines for the console trace viewer.

        The runs row is upserted first in the same call, so the trace FK never blocks (D-025).
        """
        self.client.upsert("runs", {"run_id": run_id, "kind": kind, "status": RUN_STATUS.get(status, "failed"),
                                    "finished": datetime.now(IST).isoformat(timespec="seconds"),
                                    "log_path": f"logs/trace-{run_id}.jsonl"}, on_conflict="run_id")
        self.copy_trace(run_id)

    def copy_trace(self, run_id: str) -> int:
        rows = [trace_row(run_id, seq, e) for seq, e in enumerate(self.tracer.read())]
        for i in range(0, len(rows), TRACE_BATCH):
            self.client.upsert("trace_events", rows[i:i + TRACE_BATCH], on_conflict="run_id,seq")
        return len(rows)

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

    # ----- series (WS2-21) ----------------------------------------------------------------

    def write_series(self, series: dict[str, Any], run_id: str, exclude: ExcludeFn | None = None,
                     name_for: NameFn | None = None) -> str:
        ids = list(series.get("crime_ids") or [])
        stored = self.client.select("series_members", {"select": "series_id,crime_id",
                                                       "crime_id": f"in.({','.join(ids)})"}) if ids else []
        sid = choose_series_id(series, {r["crime_id"]: r["series_id"] for r in stored})
        row: dict[str, Any] = {"series_id": sid, "name": series_name(series), "run_id": run_id, "synthetic": True}
        if name_for and sid != series.get("series_id"):
            # This run grew a STORED series but saw only its own links (e.g. a new FIR joining 3 of 10 members), so
            # the run's name describes a subset ("· 2 stations" for a 3-station series, run_0a2af3e9). Name it
            # from ALL members; if they can't be read, keep the stored name rather than write the subset's.
            have = {r["crime_id"] for r in self.client.select("series_members", {"select": "crime_id",
                                                                                 "series_id": f"eq.{sid}"})}
            gone = set(exclude(sorted(have - set(ids)))) if exclude and have - set(ids) else set()
            whole = sorted((have - gone) | set(ids))
            if set(whole) != set(ids):
                name = name_for(whole)
                if name:
                    row["name"] = name
                else:
                    row.pop("name")
        self.client.upsert("series", row, on_conflict="series_id")
        if exclude:  # D-033: only this series' members, only those `exclude` names; the crimes are never touched
            members = self.client.select("series_members", {"select": "crime_id", "series_id": f"eq.{sid}"})
            others = sorted({r["crime_id"] for r in members} - set(ids))
            gone = dict(exclude(others)) if others else {}
            for cid in others:
                if cid not in gone:
                    continue
                self.client.delete("series_members", {"series_id": f"eq.{sid}", "crime_id": f"eq.{cid}"})
                self.removed.append({"series_id": sid, "crime_id": cid, "reason": gone[cid]})
        self.client.upsert("series_members", [{"series_id": sid, "crime_id": cid} for cid in ids],
                           on_conflict="series_id,crime_id")
        self.tracer.emit("Series analyst", "series_saved", input_summary=sid,
                         output_summary=f"{len(ids)} members" + ("" if sid == series["series_id"] else
                                                                 f" (grew stored series, was {series['series_id']})"),
                         status="ok")
        return sid

    def get_features(self, crime_id: str) -> dict[str, Any] | None:
        return None  # live features come through Zetaris q_features (sb.crime_features_v)

    def write_dossier(self, series_id: str, dossier: dict[str, Any]) -> bool:
        """True when a stored series row took the dossier (an unknown id updates nothing)."""
        return bool(self.client.update("series", {"series_id": f"eq.{series_id}"}, {"dossier": dossier}))
