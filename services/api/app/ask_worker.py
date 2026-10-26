"""Ask Nexus worker (WS3-30): answers `ask_questions` rows. A separate process beside the main worker (chief, 27 Oct),
so a long case run never delays a question and Ask never touches the case runs' clients, breaker or trace.

    python -m app.ask_worker            # poll every 3 s
    python -m app.ask_worker --once     # one pass, then exit

Each pass:
  1. marks questions stuck in planning/running for more than STALE_MINUTES as failed ("timed out"), so a stopped
     worker cannot hold a user's 3-question allowance;
  2. claims the oldest queued questions one at a time with a conditional update (queued -> planning), so two
     copies of this worker never answer the same question;
  3. answers each through app.ask with its own Tracer (run "ask_<8hex>"), Zetaris and Nightshift clients, writes
     the plan and answer back and copies the trace for the console (runs.kind = 'search').
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from .adapters.nightshift import NightshiftClient
from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient
from .agents.base import AgentDeps
from .ask import AGENT, TZ, Outcome, answer_question
from .config import Settings, get_settings
from .graph.store import SupabaseStore
from .tracing import Tracer, new_run_id

STALE_MINUTES = 3
PER_PASS = 3
COLUMNS = "question_id,question,status,created_at"


def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


class AskWorker:
    def __init__(self, settings: Settings, sb: Any,
                 deps_factory: Callable[[Tracer], AgentDeps] | None = None) -> None:
        self.settings = settings
        self.sb = sb
        self.deps_factory = deps_factory or self._deps

    def _deps(self, tracer: Tracer) -> AgentDeps:
        return AgentDeps(tracer=tracer, zetaris=ZetarisClient(self.settings, tracer),
                         nightshift=NightshiftClient(self.settings, tracer), engines=None)

    def sweep_stale(self, now: datetime | None = None) -> int:
        cutoff = ((now or datetime.now(TZ)) - timedelta(minutes=STALE_MINUTES)).isoformat(timespec="seconds")
        done = self.sb.update("ask_questions", {"status": "in.(planning,running)", "started_at": f"lt.{cutoff}"},
                              {"status": "failed", "answered_at": _now(),
                               "error": f"Timed out: no answer within {STALE_MINUTES} minutes. Please ask again."})
        return len(done)

    def claim(self, qid: str) -> bool:
        got = self.sb.update("ask_questions", {"question_id": f"eq.{qid}", "status": "eq.queued"},
                             {"status": "planning", "started_at": _now()})
        return bool(got)

    def answer(self, row: dict[str, Any]) -> str:
        qid = row["question_id"]
        run_id = new_run_id("ask")
        tracer = Tracer(run_id, self.settings.logs_dir, echo=False)
        deps = self.deps_factory(tracer)
        match = {"question_id": f"eq.{qid}"}
        self.sb.update("ask_questions", match, {"run_id": run_id})

        def running() -> None:
            self.sb.update("ask_questions", match, {"status": "running"})

        try:
            out = answer_question(row["question"], deps, on_running=running)
        except Exception as exc:  # noqa: BLE001 - a bad question is marked failed; the queue keeps moving
            tracer.emit(AGENT, "ask_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300], status="error")
            out = Outcome("failed", None, None, error=f"Something went wrong: {type(exc).__name__}")
        self.sb.update("ask_questions", match, {
            "status": out.status, "plan": out.plan, "answer": out.answer, "model": out.model,
            "routed_model": out.routed_model, "receipt_id": out.receipt_id, "error": out.error,
            "answered_at": _now()})
        try:
            SupabaseStore(self.sb, tracer).finish_run(run_id, "success" if out.status != "failed" else "failed",
                                                      kind="search")
        except Exception as exc:  # noqa: BLE001 - the answer is written; a missing trace copy must not undo it
            print(f"trace copy failed for {run_id}: {exc}", flush=True)
        for client in (deps.zetaris, deps.nightshift):
            close = getattr(client, "close", None)
            if close:
                close()
        return out.status

    def run_once(self) -> dict[str, int]:
        swept = self.sweep_stale()
        queued = self.sb.select("ask_questions", {"select": COLUMNS, "status": "eq.queued",
                                                  "order": "created_at.asc", "limit": str(PER_PASS)})
        answered = 0
        for row in queued:
            if self.claim(row["question_id"]):
                self.answer(row)
                answered += 1
        return {"swept": swept, "answered": answered}


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask Nexus worker")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--interval", type=float, default=3.0, help="seconds between passes")
    args = ap.parse_args()
    s = get_settings()
    sb = SupabaseClient(s)
    if not sb.configured:
        raise SystemExit("Supabase is not configured; the Ask worker has no queue to read.")
    w = AskWorker(s, sb)
    while True:
        try:
            out = w.run_once()
            if any(out.values()):
                print(out, flush=True)
        except Exception as exc:  # a network blip must not stop the queue; the next pass retries
            if args.once:
                raise
            print(f"ask pass failed: {type(exc).__name__}: {str(exc)[:200]}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
