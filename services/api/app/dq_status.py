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

It also runs q_source_counts (WS3-27) and upserts component 'zetaris:sources': detail.counts holds the row
count of every federated source, keyed by the console Data sources page's source ids, which the page shows
"as of <checked_at>, via Zetaris". That row is written only when Zetaris itself answered: a failure or a
sample-mode answer leaves the last good row (and its real checked_at) in place.

    python -m app.dq_status [--only dq|sources]

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
SOURCES_COMPONENT = "zetaris:sources"
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


def build_sources_row(zetaris: Any) -> tuple[dict[str, Any] | None, str]:
    """The 'zetaris:sources' row for one q_source_counts call, or (None, why) when there is nothing true to
    write: Zetaris failed, or only the sample twin answered. Never raises."""
    try:
        r = zetaris.named("q_source_counts", agent=AGENT)
    except Exception as exc:
        return None, f"q_source_counts failed: {str(exc)[:200]}"
    if r.source != "zetaris":
        return None, f"answered by {r.source}, not Zetaris: not written"
    counts = {sid: int(n) for sid, n in r.rows if n is not None}
    missing = sorted(sid for sid, n in r.rows if n is None)
    detail: dict[str, Any] = {"counts": counts, "source": r.source, "ms": r.ms, "query_id": r.query_id}
    if missing:
        detail["not_measured"] = ", ".join(missing)
    return {"component": SOURCES_COMPONENT, "state": "live", "detail": detail, "checked_at": _now()}, "ok"


def run(settings: Settings, sb: Any, zetaris: Any, tracer: Tracer) -> dict[str, Any]:
    row = build_row(zetaris, _previous(sb))
    sb.upsert("system_status", [row], on_conflict="component")
    tracer.emit(AGENT, "dq_status", input_summary=COMPONENT,
                output_summary=f"state={row['state']} total={row['detail'].get('total')}",
                zetaris_query_ids=[row["detail"]["query_id"]] if "query_id" in row["detail"] else [],
                status="ok" if row["state"] != "down" else "error")
    return row


def run_sources(sb: Any, zetaris: Any, tracer: Tracer) -> tuple[dict[str, Any] | None, str]:
    row, why = build_sources_row(zetaris)
    if row is not None:
        sb.upsert("system_status", [row], on_conflict="component")
    tracer.emit(AGENT, "source_counts", input_summary=SOURCES_COMPONENT,
                output_summary=f"written sources={len(row['detail']['counts'])}" if row else why,
                zetaris_query_ids=[row["detail"]["query_id"]] if row else [],
                status="ok" if row else "error")
    return row, why


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m app.dq_status", description=__doc__.splitlines()[0])
    ap.add_argument("--only", choices=("dq", "sources"), help="run just one of the two (default: both)")
    args = ap.parse_args(argv)
    s = get_settings()
    sb = SupabaseClient(s)
    if not sb.configured:
        raise SystemExit("Supabase is not configured; nowhere to write system_status.")
    tracer = Tracer(new_run_id("dqstatus"), s.logs_dir, echo=False)
    z = ZetarisClient(s, tracer)
    row = src = None
    why = ""
    try:
        if args.only != "sources":
            row = run(s, sb, z, tracer)
        if args.only != "dq":
            src, why = run_sources(sb, z, tracer)
    finally:
        z.close()
        sb.close()
    if row is not None:
        d = row["detail"]
        print(f"{COMPONENT}: {row['state']} total={d.get('total')} source={d.get('source')} ms={d.get('ms')}"
              + (f" not_measured={d['not_measured']}" if d.get("not_measured") else "")
              + (f" error={d['error']}" if d.get("error") else ""), flush=True)
    if args.only != "dq":
        if src is not None:
            d = src["detail"]
            print(f"{SOURCES_COMPONENT}: written {len(d['counts'])} sources ms={d['ms']}"
                  + (f" not_measured={d['not_measured']}" if d.get("not_measured") else ""), flush=True)
        else:
            print(f"{SOURCES_COMPONENT}: not written ({why})", flush=True)


if __name__ == "__main__":
    main()
