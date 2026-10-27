"""File-backed store for live runs without Supabase (WS2-22).

A fresh clone with Zetaris and Nightshift but no Supabase keys still keeps its results: alerts (with their
factors), series + members, Extractor features and runs go to JSON files under `data/local/` (gitignored;
`NEXUS_LOCAL_DIR` overrides). The Extractor reads features back, so a restart does not re-extract.

Behaviour follows SupabaseStore wherever it differs from MemoryStore:
- `status` on alerts and series is never overwritten by the agents (an analyst's decision survives);
- a series id stays stable as the series grows (`choose_series_id`), D-033 removals are recorded in
  `removed` for the runner to trace;
- `write_dossier` only updates a stored series (an unknown id returns False);
- runs map to success / failed. Traces are not copied: they are already in `logs/trace-<run_id>.jsonl`.

Notifications stay in memory (there is no console reading this store). The worker is Supabase-only.

Every write is a locked read-modify-write of one file, saved through a temp file in the same directory and
`os.replace`, so concurrent runs in the API's thread pool lose nothing and a crash never leaves half a file.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ..agents.base import ExcludeFn, NameFn, choose_series_id, series_name
from ..config import Settings
from ..tracing import IST
from .store import RUN_STATUS

STORE_KINDS = ("supabase", "local", "memory")
_LOCK = threading.RLock()  # one per process: every LocalStore instance shares it


def store_kind(settings: Settings) -> str:
    """Which store a run uses. One pure function, so /health and the runner can never disagree.

    `NEXUS_STORE` wins when set. Otherwise: Supabase when configured; else memory in sample mode (judge
    fixtures stay byte-stable) and local files in live mode.
    """
    configured = bool(settings.supabase_url and settings.supabase_service_role_key)
    want = (settings.nexus_store or "").strip().lower()
    if want:
        if want not in STORE_KINDS:
            raise ValueError(f"NEXUS_STORE={settings.nexus_store!r}: expected one of {', '.join(STORE_KINDS)}")
        if want == "supabase" and not configured:
            raise ValueError("NEXUS_STORE=supabase but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set")
        return want
    if configured:
        return "supabase"
    return "memory" if settings.sample_mode else "local"


class LocalStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.removed: list[dict[str, Any]] = []  # series_member_removed rows (D-033); the runner traces them
        self.notifications: list[dict[str, Any]] = []

    # ----- files ----------------------------------------------------------------------------------

    def _read(self, name: str) -> dict[str, Any]:
        path = self.root / f"{name}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8") or "{}")

    def _write(self, name: str, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)  # lazily, on the first write
        fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True, default=str)
            os.replace(tmp, self.root / f"{name}.json")
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _update(self, name: str, fn: Callable[[dict[str, Any]], Any]) -> Any:
        with _LOCK:
            data = self._read(name)
            out = fn(data)
            self._write(name, data)
            return out

    # ----- reads (tests, and the Extractor) ---------------------------------------------------------

    def get_features(self, crime_id: str) -> dict[str, Any] | None:
        with _LOCK:
            return self._read("crime_features").get(crime_id)

    def alerts(self) -> dict[str, Any]:
        with _LOCK:
            return self._read("link_alerts")

    def series(self) -> dict[str, Any]:
        with _LOCK:
            return self._read("series")

    def runs(self) -> dict[str, Any]:
        with _LOCK:
            return self._read("runs")

    # ----- runs -------------------------------------------------------------------------------------

    def start_run(self, run_id: str, kind: str, log_path: str, subject: str | None = None) -> None:
        row = {"run_id": run_id, "kind": kind, "status": "running", "log_path": log_path,
               "started": datetime.now(IST).isoformat(timespec="seconds")}
        if subject:
            row["subject"] = subject
        self._update("runs", lambda d: d.__setitem__(run_id, {**d.get(run_id, {}), **row}))

    def finish_run(self, run_id: str, status: str, kind: str = "case") -> None:
        row = {"run_id": run_id, "kind": kind, "status": RUN_STATUS.get(status, "failed"),
               "finished": datetime.now(IST).isoformat(timespec="seconds"), "log_path": f"logs/trace-{run_id}.jsonl"}
        self._update("runs", lambda d: d.__setitem__(run_id, {**d.get(run_id, {}), **row}))

    # ----- Store protocol ---------------------------------------------------------------------------

    def upsert_features(self, features: dict[str, Any]) -> None:
        self._update("crime_features", lambda d: d.__setitem__(features["crime_id"], features))

    def write_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        def put(d: dict[str, Any]) -> None:
            old = d.get(alert["alert_id"])
            row = dict(alert)
            if old and "status" in old:  # agents never overwrite a decision
                row["status"] = old["status"]
            d[alert["alert_id"]] = row

        self._update("link_alerts", put)
        return alert

    def notify(self, notifications: list[dict[str, Any]]) -> None:
        self.notifications.extend(notifications)

    def write_series(self, series: dict[str, Any], run_id: str, exclude: ExcludeFn | None = None,
                     name_for: NameFn | None = None) -> str:
        ids = set(series.get("crime_ids") or [])

        def put(d: dict[str, Any]) -> str:
            existing = {cid: sid for sid, s in d.items() for cid in s.get("crime_ids") or []}
            sid = choose_series_id(series, existing)
            row = d.setdefault(sid, {"series_id": sid, "crime_ids": [], "dossier": None, "status": "candidate"})
            others = sorted(set(row["crime_ids"]) - ids)
            gone = dict(exclude(others)) if exclude and others else {}
            for cid in others:
                if cid in gone:
                    self.removed.append({"series_id": sid, "crime_id": cid, "reason": gone[cid]})
            row.update(name=series_name(series), run_id=run_id, synthetic=True,
                       crime_ids=sorted((set(row["crime_ids"]) - set(gone)) | ids))
            return sid

        return self._update("series", put)

    def write_dossier(self, series_id: str, dossier: dict[str, Any]) -> bool:
        def put(d: dict[str, Any]) -> bool:
            if series_id not in d:
                return False
            d[series_id]["dossier"] = dossier
            return True

        return self._update("series", put)
