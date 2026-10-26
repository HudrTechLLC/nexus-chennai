"""Background worker (spec C2, LANES §2 "Web <-> backend"). Task WS2-16.

    python -m app.worker            # poll forever
    python -m app.worker --once     # one pass (tests, cron)

The console on Vercel cannot reach the laptop API, so it writes to Supabase and this
worker picks the work up:

1. `alert_decisions` with processed_at null -> H-MEM `record_decision` (the memory that
   changes future scores, LNK-08), `link_alerts.status`, notifications to both stations
   and, on approval, a joint-case proposal (LNK-09).
2. `tips` with status 'new' -> Tip Guard (Scout Intent). Each tip gets its guard verdict
   and a status of screened, quarantined or urgent. Nothing else reads a tip before this (R8).
3. New crimes without `crime_features` -> the agent graph (extract -> link -> Skeptic -> alerts).

Queue and state rows come from Supabase. The crime facts behind an H-MEM memory are read
through Zetaris named queries (R1).
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from typing import Any

from . import engines
from .adapters.nightshift import NightshiftClient
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient
from .agents import AgentDeps, TipGuard, hmem_pair
from .agents.base import crime_from_row, features_from_row, rows_as_dicts
from .config import Settings, get_settings
from .graph.runner import run_request
from .graph.store import SupabaseStore
from .tracing import IST, Tracer, new_run_id

BATCH = 25
STATUS_FOR_DECISION = {"approve": "approved", "reject": "rejected"}
TIP_STATUS = {"clean": "screened", "quarantine": "quarantined", "urgent": "urgent"}


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


class Worker:
    def __init__(self, settings: Settings, sb: Any, zetaris: Any = None, nightshift: Any = None,
                 tracer: Tracer | None = None, run_case=None) -> None:
        self.settings = settings
        self.sb = sb
        self.tracer = tracer or Tracer(new_run_id("worker"), settings.logs_dir)
        self.zetaris = zetaris or ZetarisClient(settings, self.tracer)
        self.nightshift = nightshift or NightshiftClient(settings, self.tracer)
        self.run_case = run_case or (lambda cid: run_request("case", {"crime_id": cid}, {}, settings,
                                                             store_factory=lambda s, t: SupabaseStore(sb, t)))
        self.deps = AgentDeps(tracer=self.tracer, zetaris=self.zetaris, nightshift=self.nightshift, engines=engines)

    # ----- 1. analyst decisions -> H-MEM ---------------------------------------------

    def _pair_for(self, crimes: list[str]) -> dict[str, Any]:
        cases = {}
        for cid in crimes[:2]:
            rows = rows_as_dicts(self.zetaris.named("q_case", agent="Worker", crime_id=cid))
            if rows:
                cases[cid] = crime_from_row(rows[0])
        feats = {r.get("crime_id"): features_from_row(r) for r in rows_as_dicts(
            self.zetaris.named("q_features", agent="Worker", ids=",".join(crimes[:2])))}
        a, b = (cases.get(c, {"crime_id": c}) for c in crimes[:2])
        return hmem_pair(a, feats.get(crimes[0]), b, feats.get(crimes[1]))

    def process_decisions(self) -> int:
        rows = self.sb.select("alert_decisions", {"select": "*", "processed_at": "is.null", "order": "at.asc",
                                                  "limit": str(BATCH)})
        done = 0
        for d in rows:
            alert_id = d["alert_id"]
            alerts = self.sb.select("link_alerts", {"select": "alert_id,crimes,stations,band",
                                                    "alert_id": f"eq.{alert_id}"})
            if not alerts:
                self.sb.update("alert_decisions", {"decision_id": f"eq.{d['decision_id']}"}, {"processed_at": _now()})
                continue
            alert = alerts[0]
            pair = self._pair_for(list(alert["crimes"]))
            engines.hmem.record_decision(alert_id, d["decision"], d.get("reason_code"), d.get("note"), pair)
            self.sb.update("link_alerts", {"alert_id": f"eq.{alert_id}"},
                           {"status": STATUS_FOR_DECISION[d["decision"]]})
            self._notify_decision(alert, d)
            self.sb.update("alert_decisions", {"decision_id": f"eq.{d['decision_id']}"}, {"processed_at": _now()})
            self.tracer.emit("Worker", "decision_to_memory", input_summary=f"{alert_id} {d['decision']}",
                             output_summary=f"reason={d.get('reason_code')}", engine="hmem", status="ok")
            done += 1
        return done

    def _notify_decision(self, alert: dict[str, Any], d: dict[str, Any]) -> None:
        stations = list(alert.get("stations") or [])
        if not stations:
            return
        users = self.sb.select("profiles", {"select": "user_id", "station_id": f"in.({','.join(stations)})"})
        if d["decision"] == "approve":
            title = f"Link {alert['alert_id']} approved: joint case proposed for {' + '.join(stations)}"
            kind = "joint_case_proposal"
        else:
            title = f"Link {alert['alert_id']} rejected ({d.get('reason_code')})"
            kind = "alert_decision"
        rows = [{"user_id": u["user_id"], "kind": kind, "title": title, "body": d.get("note"),
                 "link": f"/console/alerts/{alert['alert_id']}"} for u in users]
        if rows:
            self.sb.insert("notifications", rows)

    # ----- 2. tips -> Tip Guard -------------------------------------------------------------

    def process_tips(self) -> int:
        tips = self.sb.select("tips", {"select": "tip_id,text,category", "status": "eq.new", "limit": str(BATCH)})
        guard = TipGuard(self.deps)
        for t in tips:
            screened = guard.screen(t)
            g = screened["guard"]
            stored_guard = {k: g.get(k) for k in ("verdict", "intent", "risk", "injection", "threat", "emergency")}
            self.sb.update("tips", {"tip_id": f"eq.{t['tip_id']}"},
                           {"guard": stored_guard, "status": TIP_STATUS[g["verdict"]]})
        return len(tips)

    # ----- 3. new cases -> agent graph ---------------------------------------------------------

    def process_new_cases(self) -> int:
        recent = self.sb.select("crimes", {"select": "crime_id", "order": "reported_at.desc", "limit": str(BATCH)})
        ids = [r["crime_id"] for r in recent]
        if not ids:
            return 0
        have = {r["crime_id"] for r in self.sb.select("crime_features", {"select": "crime_id",
                                                                         "crime_id": f"in.({','.join(ids)})"})}
        todo = [cid for cid in ids if cid not in have]
        for cid in todo:
            try:
                self.run_case(cid)
            except Exception as exc:  # one bad case must not stop the queue
                self.tracer.emit("Worker", "case_failed", input_summary=cid, output_summary=str(exc)[:300],
                                 status="error")
        return len(todo)

    # ----- 4. system status heartbeat (console /console/system) -----------------------------

    def _probe(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        def add(component: str, state: str, **detail: Any) -> None:
            rows.append({"component": component, "state": state, "detail": detail, "checked_at": _now()})

        try:
            r = self.zetaris.named("q_ping", agent="Worker")
            add("zetaris", "sample" if r.source == "sample" else "live", ms=r.ms)
        except Exception as exc:
            add("zetaris", "down", error=str(exc)[:200])
        try:
            served = set(self.nightshift.list_models())
            for lane, model in self.settings.lanes.items():
                add(f"nightshift:{lane}", "live" if model in served else "degraded", model=model)
        except Exception as exc:
            state = "sample" if self.settings.sample_mode else "down"
            for lane, model in self.settings.lanes.items():
                add(f"nightshift:{lane}", state, model=model, error=str(exc)[:200])
        add("engines", "live", backend=engines.backend())
        add("supabase", "live")
        add("worker", "live", interval_note="heartbeat each pass")
        return rows

    def heartbeat(self) -> int:
        """Write system_status. Never fails a worker pass (D-025): errors are traced and skipped."""
        try:
            rows = self._probe()
            self.sb.upsert("system_status", rows, on_conflict="component")
            return len(rows)
        except Exception as exc:
            self.tracer.emit("Worker", "heartbeat_failed", output_summary=str(exc)[:300], status="error")
            return 0

    def run_once(self) -> dict[str, int]:
        self.heartbeat()
        with engines.use_tracer(self.tracer):
            out = {"decisions": self.process_decisions(), "tips": self.process_tips()}
        out["cases"] = self.process_new_cases()
        return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Nexus background worker")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between passes")
    args = ap.parse_args()
    s = get_settings()
    sb = SupabaseClient(s)
    if not sb.configured:
        raise SystemExit("Supabase is not configured; the worker has no queue to read.")
    w = Worker(s, sb)
    while True:
        print(w.run_once(), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
