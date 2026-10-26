"""Data-quality counts for the console System page (D-029).

    python -m app.dq_status

Vercel cannot reach Zetaris, so the System page cannot run the data-quality views itself. This script
runs the named query q_dq_summary once (the 7 rule views in zetaris/20_dq.sql; about 80 s live) and
upserts one system_status row, component 'zetaris:dq', which the page shows next to the worker's
heartbeat rows:

- state 'live' when Zetaris answered, 'sample' when the DuckDB twin over data/sample answered (the
  counts are then for the bundle, and rules it cannot measure are listed under not_measured), and
  'down' when the query failed (the last good counts are kept under last_ok);
- detail: one key per rule with its row count, total, source, ms, and the Zetaris query id (the trace
  file of this run records the same id).

It is separate from the worker on purpose: the worker's pass is synchronous, and an 80 s query on every
heartbeat would hold up new FIRs. Run it after a re-seed and before a demo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .adapters.supabase import SupabaseClient
from .adapters.zetaris import ZetarisClient
from .adapters.zetaris_queries_n1 import DQ_RULE_VIEWS
from .config import Settings, get_settings
from .tracing import IST, Tracer, new_run_id

COMPONENT = "zetaris:dq"
AGENT = "DQStatus"
RULES = tuple(rule for rule, _ in DQ_RULE_VIEWS)


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def _previous(sb: Any) -> dict[str, Any] | None:
    try:
        rows = sb.select("system_status", {"select": "state,detail,checked_at", "component": f"eq.{COMPONENT}"})
    except Exception:
        return None
    return rows[0] if rows else None


def build_row(zetaris: Any, previous: dict[str, Any] | None) -> dict[str, Any]:
    """The system_status row for one q_dq_summary call. Never raises."""
    checked = _now()
    try:
        r = zetaris.named("q_dq_summary", agent=AGENT)
    except Exception as exc:
        detail: dict[str, Any] = {"error": str(exc)[:200]}
        if previous:
            prev = previous.get("detail") or {}
            # Keep the last good counts; a 'down' row carries them forward unchanged.
            if previous.get("state") == "down":
                last = prev.get("last_ok")
            else:
                last = {k: prev.get(k) for k in RULES if k in prev}
                last.update(source=prev.get("source"), checked_at=previous.get("checked_at"))
            if last:
                detail["last_ok"] = last
        return {"component": COMPONENT, "state": "down", "detail": detail, "checked_at": checked}
    counts = {rule: (None if n is None else int(n)) for rule, n in r.rows}
    detail = {**counts, "total": sum(n for n in counts.values() if n is not None), "source": r.source,
              "ms": r.ms, "query_id": r.query_id}
    missing = sorted(k for k, v in counts.items() if v is None)
    if missing:
        detail["not_measured"] = ", ".join(missing)
    return {"component": COMPONENT, "state": "sample" if r.source == "sample" else "live", "detail": detail,
            "checked_at": checked}


def run(settings: Settings, sb: Any, zetaris: Any, tracer: Tracer) -> dict[str, Any]:
    row = build_row(zetaris, _previous(sb))
    sb.upsert("system_status", [row], on_conflict="component")
    tracer.emit(AGENT, "dq_status", input_summary=COMPONENT,
                output_summary=f"state={row['state']} total={row['detail'].get('total')}",
                zetaris_query_ids=[row["detail"]["query_id"]] if "query_id" in row["detail"] else [],
                status="ok" if row["state"] != "down" else "error")
    return row


def main() -> None:
    s = get_settings()
    sb = SupabaseClient(s)
    if not sb.configured:
        raise SystemExit("Supabase is not configured; nowhere to write system_status.")
    tracer = Tracer(new_run_id("dqstatus"), s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    try:
        row = run(s, sb, z, tracer)
    finally:
        z.close()
        sb.close()
    d = row["detail"]
    print(f"{COMPONENT}: {row['state']} total={d.get('total')} source={d.get('source')} ms={d.get('ms')}"
          + (f" not_measured={d['not_measured']}" if d.get("not_measured") else "")
          + (f" error={d['error']}" if d.get("error") else ""), flush=True)


if __name__ == "__main__":
    main()
