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
2b. `appeal_requests` -> Sanitiser drafts in `public_incidents`.
2c. `series` with no dossier -> Series analyst (Markovian), stored in `series.dossier`.
3. New crimes (reported_at <= now) without `crime_features` -> the agent graph (extract -> link ->
   Skeptic -> alerts); the run row carries subject = crime_id so the console can link its trace.
3b. `onboarding_runs` (WS1-23, 0007_15): a new source's export uploaded -> profiled through Zetaris, mapped by
   the fast lane, DQ-checked -> proposed; approved -> registered as a Zetaris view (not linked). See onboarding.py.
4. Stale runs: a run still 'running' with no trace event for STALE_RUN_MINUTES (its process was
   stopped) becomes 'interrupted' (0006_04), with a run_interrupted event and its trace copied.

Queue and state rows come from Supabase. The crime facts behind an H-MEM memory are read
through Zetaris named queries (R1).

The worker is Supabase-only (WS2-22): its queues (decisions, tips, appeal requests, new FIRs) are
written by the console, which only Supabase connects. `NEXUS_STORE=local` affects /run and the
API, never the worker; without Supabase keys the worker has nothing to poll.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import engines
from .adapters.nightshift import NightshiftClient
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient
from .agents import AgentDeps, Sanitiser, TipGuard, hmem_pair
from .agents.base import crime_from_row, features_from_row, rows_as_dicts
from .agents.series import SeriesAnalyst, dossier_record
from .config import Settings, get_settings
from .graph.runner import run_request
from .graph.store import SupabaseStore
from .tracing import IST, Tracer, new_run_id

BATCH = 25
STATUS_FOR_DECISION = {"approve": "approved", "reject": "rejected"}
TIP_STATUS = {"clean": "screened", "quarantine": "quarantined", "urgent": "urgent"}
STALE_RUN_MINUTES = 15
# A run whose trace file is not on this machine (another lane's checkout) shows no live events here:
# trace_events reach the DB only at finish_run. Only call it interrupted after this long.
STALE_UNSEEN_RUN_HOURS = 6
SWEEP_EVERY_SECONDS = 60


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


class Worker:
    def __init__(self, settings: Settings, sb: Any, zetaris: Any = None, nightshift: Any = None,
                 tracer: Tracer | None = None, run_case=None, new_cases_since: str | None = None) -> None:
        self.settings = settings
        # When set, only crimes created after this instant (console-filed FIRs) are processed; the
        # priority backfill owns the seeded backlog until it finishes (chief, 26 Oct).
        self.new_cases_since = new_cases_since
        self.sb = sb
        self.tracer = tracer or Tracer(new_run_id("worker"), settings.logs_dir)
        self.zetaris = zetaris or ZetarisClient(settings, self.tracer)
        self.nightshift = nightshift or NightshiftClient(settings, self.tracer)
        case_settings = settings.model_copy(update={"run_deadline_seconds": settings.case_run_deadline_seconds})
        self.run_case = run_case or (lambda cid: run_request("case", {"crime_id": cid}, {}, case_settings,
                                                             store_factory=lambda s, t: SupabaseStore(sb, t)))
        self.deps = AgentDeps(tracer=self.tracer, zetaris=self.zetaris, nightshift=self.nightshift, engines=engines)
        self._dossier_failed: set[str] = set()
        self._last_sweep = 0.0
        self.logs_dir = Path(settings.logs_dir)  # where runs on this machine write their live trace files

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
            # LNK-09: analysts+ propose the task force and a supervisor approves it (city-wide roles).
            users = users + self.sb.select("profiles", {"select": "user_id", "role": "in.(analyst,supervisor)"})
        else:
            title = f"Link {alert['alert_id']} rejected ({d.get('reason_code')})"
            kind = "alert_decision"
        users = list({u["user_id"]: u for u in users}.values())
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
            stored_guard = {k: g.get(k) for k in ("verdict", "intent", "risk", "injection", "threat", "emergency",
                                                     "summary", "tags")}
            self.sb.update("tips", {"tip_id": f"eq.{t['tip_id']}"},
                           {"guard": stored_guard, "status": TIP_STATUS[g["verdict"]]})
        return len(tips)

    # ----- 2b. public appeal draft requests -> Sanitiser (WS4-07) ---------------------------

    PUBLIC_INCIDENT_COLUMNS = ("public_incident_id", "title", "category", "area_label", "cell", "week",
                               "time_window", "summary", "looking_for", "images", "sanitiser_model")

    def process_appeal_requests(self) -> int:
        reqs = self.sb.select("appeal_requests", {"select": "request_id,crime_id", "status": "eq.requested",
                                                  "order": "requested_at.asc", "limit": str(BATCH)})
        san = Sanitiser(self.deps)
        for r in reqs:
            match = {"request_id": f"eq.{r['request_id']}"}
            try:
                cases = rows_as_dicts(self.zetaris.named("q_case", agent="Sanitiser", crime_id=r["crime_id"]))
                if not cases:
                    raise ValueError(f"case {r['crime_id']} not found")
                feats = rows_as_dicts(self.zetaris.named("q_features", agent="Sanitiser", ids=r["crime_id"]))
                draft = san.draft(crime_from_row(cases[0]), features_from_row(feats[0]) if feats else None)
                row = {k: draft.get(k) for k in self.PUBLIC_INCIDENT_COLUMNS}
                row.update(crime_id=r["crime_id"], status="draft", synthetic=True)
                self.sb.upsert("public_incidents", row, on_conflict="public_incident_id")
                self.sb.update("appeal_requests", match, {"status": "drafted", "processed_at": _now(),
                                                          "public_incident_id": draft["public_incident_id"]})
            except Exception as exc:  # a bad request is marked failed; the queue keeps moving
                self.sb.update("appeal_requests", match, {"status": "failed", "processed_at": _now(),
                                                          "error": str(exc)[:300]})
                self.tracer.emit("Sanitiser", "appeal_request_failed", input_summary=str(r["request_id"]),
                                 output_summary=str(exc)[:300], status="error")
        return len(reqs)

    # ----- 2c. series without a dossier -> Series analyst (WS2-21) --------------------------

    DOSSIERS_PER_PASS = 1  # reason-lane chunks; keep a pass short
    DOSSIER_SECONDS = 180  # chunks past this fall back to the extractive generator (traced)

    def process_dossiers(self) -> int:
        series = self.sb.select("series", {"select": "series_id", "dossier": "is.null", "order": "created_at.asc",
                                           "limit": str(self.DOSSIERS_PER_PASS + len(self._dossier_failed))})
        todo = [r["series_id"] for r in series if r["series_id"] not in self._dossier_failed]
        done = 0
        for sid in todo[: self.DOSSIERS_PER_PASS]:
            try:
                members = [r["crime_id"] for r in self.sb.select("series_members", {
                    "select": "crime_id", "series_id": f"eq.{sid}", "order": "crime_id.asc"})]
                deps = replace(self.deps, deadline=time.monotonic() + self.DOSSIER_SECONDS)
                out = SeriesAnalyst(deps).dossier(sid, members)
                SupabaseStore(self.sb, self.tracer).write_dossier(sid, dossier_record(out, self.tracer.run_id))
                done += 1
            except Exception as exc:  # retried by the next worker process, not every pass
                self._dossier_failed.add(sid)
                self.tracer.emit("Series analyst", "dossier_failed", input_summary=sid,
                                 output_summary=str(exc)[:300], status="error")
        return done

    # ----- 3. new cases -> agent graph ---------------------------------------------------------

    def process_onboarding(self) -> int:
        """WS1-23: one uploaded and one approved onboarding run per pass. Never fails a worker pass."""
        from .onboarding import Onboarder

        try:
            return Onboarder(self.settings, self.sb, self.zetaris, self.nightshift, self.logs_dir).process()
        except Exception as exc:  # e.g. 0007_15 not applied yet
            self.tracer.emit("Worker", "onboarding_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300],
                             status="error")
            return 0

    def process_new_cases(self) -> int:
        # reported_at <= now: seed rows dated in the future must not crowd a just-filed FIR out of the batch.
        params = {"select": "crime_id", "reported_at": f"lte.{_now()}", "order": "reported_at.desc",
                  "limit": str(BATCH)}
        if self.new_cases_since:
            params["created_at"] = f"gt.{self.new_cases_since}"
        recent = self.sb.select("crimes", params)
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

    # ----- 5. stale runs -> interrupted (0006_04) ----------------------------------------

    def _last_event_at(self, run: dict[str, Any]) -> tuple[datetime, bool]:
        """(newest sign of life, seen live). The run's local trace file is written live; trace_events
        reach the DB only at finish_run, so without the file we fall back to its newest stored event,
        else when it started, and say the run was not seen live."""
        path = self.logs_dir / f"trace-{run['run_id']}.jsonl"
        if path.is_file():
            for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
                try:
                    return datetime.fromisoformat(json.loads(line)["timestamp"]), True
                except (ValueError, KeyError, TypeError):
                    continue
        rows = self.sb.select("trace_events", {"select": "ts", "run_id": f"eq.{run['run_id']}",
                                               "order": "ts.desc", "limit": "1"})
        if rows and rows[0].get("ts"):
            return datetime.fromisoformat(str(rows[0]["ts"])), False
        return datetime.fromisoformat(str(run["started"])), False

    def sweep_stale_runs(self, now: str | None = None) -> int:
        """Mark runs whose process was stopped as 'interrupted'. Never fails a worker pass."""
        at = datetime.fromisoformat(now) if now else datetime.now(IST)
        swept = 0
        try:
            for run in self.sb.select("runs", {"select": "run_id,kind,started", "status": "eq.running"}):
                last, seen = self._last_event_at(run)
                limit = timedelta(minutes=STALE_RUN_MINUTES) if seen else timedelta(hours=STALE_UNSEEN_RUN_HOURS)
                if at - last < limit:
                    continue
                rid = run["run_id"]
                last_iso = last.isoformat(timespec="seconds")
                run_tracer = Tracer(rid, self.logs_dir, echo=False)
                run_tracer.emit("Worker", "run_interrupted", input_summary=rid,
                                output_summary=json.dumps({"last_event_at": last_iso}),
                                status="interrupted")
                # Only a run that is still 'running' (it may have finished meanwhile).
                self.sb.update("runs", {"run_id": f"eq.{rid}", "status": "eq.running"},
                               {"status": "interrupted", "finished": at.isoformat(timespec="seconds")})
                SupabaseStore(self.sb, run_tracer).copy_trace(rid)
                self.tracer.emit("Worker", "run_interrupted", input_summary=rid,
                                 output_summary=f"no trace event since {last_iso}", status="interrupted")
                swept += 1
        except Exception as exc:
            self.tracer.emit("Worker", "sweep_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300],
                             status="error")
        return swept

    def run_once(self) -> dict[str, int]:
        """One pass. New cases (a just-filed FIR) run before dossiers, and a pass that ran a case skips the
        dossier step, so a FIR never waits behind up to DOSSIER_SECONDS of reason-lane chunks."""
        self.heartbeat()
        if time.monotonic() - self._last_sweep >= SWEEP_EVERY_SECONDS:
            self._last_sweep = time.monotonic()
            self.sweep_stale_runs()
        with engines.use_tracer(self.tracer):
            out = {"decisions": self.process_decisions(), "tips": self.process_tips(),
                   "appeals": self.process_appeal_requests()}
        out["onboarding"] = self.process_onboarding()
        out["cases"] = self.process_new_cases()
        with engines.use_tracer(self.tracer):
            out["dossiers"] = 0 if out["cases"] else self.process_dossiers()
        return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Nexus background worker")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between passes")
    ap.add_argument("--new-cases-since", default=None,
                    help="only process crimes created after this ISO time ('now' = worker start): console FIRs only")
    args = ap.parse_args()
    s = get_settings()
    sb = SupabaseClient(s)
    if not sb.configured:
        raise SystemExit("Supabase is not configured; the worker has no queue to read.")
    since = _now() if args.new_cases_since == "now" else args.new_cases_since
    w = Worker(s, sb, new_cases_since=since)
    while True:
        try:
            print(w.run_once(), flush=True)
        except Exception as exc:  # a network blip (DNS, TLS) must not stop the queue; the next pass retries
            if args.once:
                raise
            w.tracer.emit("Worker", "pass_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300], status="error")
            print(f"pass failed: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
