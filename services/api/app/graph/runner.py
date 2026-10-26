"""Runs the agent graph for one request and shapes the Part H `/run` response. Task WS2-16.

Wires the real adapters (Zetaris, Nightshift), the engines facade bound to this run's
tracer, a store and the hard deadline. Sample mode uses the same graph and agent logic;
only the adapters switch to DuckDB over data/sample and recorded model fixtures (R6).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from collections.abc import Callable, Mapping
from typing import Any

from .. import engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.supabase import SupabaseClient
from ..adapters.zetaris import ZetarisClient
from ..agents import AgentDeps, MemoryStore, Store, detect_series
from ..config import Settings
from ..tracing import Tracer, new_run_id
from .pipeline import AgentGraph
from .store import SupabaseStore

AGENTS = [
    {"name": "Scout Intent", "role": "routes events and screens tips"},
    {"name": "Tip Guard", "role": "keeps unsafe public input away from agents"},
    {"name": "Extractor", "role": "reads narratives, statements and images into MO features"},
    {"name": "Planner", "role": "plans Zetaris queries"},
    {"name": "Linker", "role": "scores pairs in code and explains them"},
    {"name": "Skeptic", "role": "re-queries Zetaris and challenges links"},
    {"name": "Alert writer", "role": "writes approved link alerts"},
    {"name": "Series analyst", "role": "groups linked cases into series and builds dossiers"},
]
ENGINES = ["world_model", "hmem", "scout_intent", "markovian"]
MAX_BATCH = 50


def _alert_view(a: Mapping[str, Any]) -> dict[str, Any]:
    return {k: a.get(k) for k in ("alert_id", "kind", "crimes", "stations", "score", "band", "coverage", "factors",
                                  "memory_applied", "skeptic", "rationale", "recommended_action", "status")}


def summarise(alerts: list[dict[str, Any]], struck_pairs: int, dropped: int, extra: str = "") -> str:
    high = sum(1 for a in alerts if a.get("band") == "high")
    med = sum(1 for a in alerts if a.get("band") == "medium")
    cross = sum(1 for a in alerts if len(set(a.get("stations") or [])) > 1)
    s = f"{len(alerts)} new links ({high} high, {med} medium; {cross} cross-station)"
    s += f"; {struck_pairs} with factors struck by Skeptic; {dropped} dropped"
    return s + (f"; {extra}" if extra else "")


@contextmanager
def agent_deps(settings: Settings, run_id: str, *, zetaris: Any = None, nightshift: Any = None
               ) -> Iterator[AgentDeps]:
    """Deps for one API call outside /run (drafts, dossiers, briefings): real adapters, traced, deadline."""
    tracer = Tracer(run_id, settings.logs_dir)
    z = zetaris or ZetarisClient(settings, tracer)
    n = nightshift or NightshiftClient(settings, tracer)
    try:
        with engines.use_tracer(tracer):
            yield AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=engines,
                            deadline=time.monotonic() + settings.run_deadline_seconds)
    finally:
        if zetaris is None:
            z.close()
        if nightshift is None:
            n.close()


def default_store(settings: Settings, tracer: Tracer) -> Store:
    """Supabase when configured (live and sample runs alike persist), else in-memory."""
    sb = SupabaseClient(settings)
    return SupabaseStore(sb, tracer) if sb.configured else MemoryStore()


def run_request(
    kind: str,
    payload: Mapping[str, Any],
    options: Mapping[str, Any] | None,
    settings: Settings,
    *,
    run_id: str | None = None,
    store_factory: Callable[[Settings, Tracer], Store] | None = None,
    zetaris: Any = None,
    nightshift: Any = None,
) -> dict[str, Any]:
    options = dict(options or {})
    if options.get("sample_mode") is not None:
        settings = settings.model_copy(update={"sample_mode": bool(options["sample_mode"])})
    run_id = run_id or new_run_id()
    tracer = Tracer(run_id, settings.logs_dir)
    started = time.perf_counter()
    deadline = time.monotonic() + settings.run_deadline_seconds
    z = zetaris or ZetarisClient(settings, tracer)
    n = nightshift or NightshiftClient(settings, tracer)
    if options.get("persist") is False:
        store: Store = MemoryStore()
    else:
        store = (store_factory or default_store)(settings, tracer)
    if isinstance(store, SupabaseStore):
        store.start_run(run_id, kind, f"logs/trace-{run_id}.jsonl")
    tracer.emit("api", "run_received", input_summary=f"kind={kind}", status="ok",
                output_summary=f"sample_mode={settings.sample_mode} deadline={settings.run_deadline_seconds}s")
    status = "failed"
    try:
        with engines.use_tracer(tracer):
            deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=engines, store=store, deadline=deadline)
            graph = AgentGraph(deps)
            output, status = _dispatch(graph, kind, payload, options)
    except Exception as exc:
        tracer.emit("api", "run_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300], status="error")
        raise
    finally:
        if zetaris is None:
            z.close()
        if nightshift is None:
            n.close()
        if isinstance(store, SupabaseStore):
            store.finish_run(run_id, status)
    elapsed = round(time.perf_counter() - started, 2)
    tracer.emit("api", "run_finished", output_summary=f"{status} in {elapsed}s", status=status)
    return {
        "run_id": run_id,
        "status": status,
        "output": output,
        "agents": AGENTS,
        "engines": ENGINES,
        "trace_id": f"trace-{run_id}",
        "log_file": f"logs/trace-{run_id}.jsonl",
        "execution_time_seconds": elapsed,
    }


def _case_output(state: Mapping[str, Any]) -> tuple[list[dict], int, int]:
    alerts = [_alert_view(a) for a in state.get("alerts", [])]
    struck = sum(1 for r in [*state.get("approved", []), *state.get("dropped", [])] if r.struck)
    return alerts, struck, len(state.get("dropped", []))


HOTSPOT_WINDOW_DAYS = 7


def _hotspots(graph: AgentGraph, case_dates: list[str], case_ids: set[str], options: Mapping[str, Any]
              ) -> tuple[list[dict[str, Any]], list[str]]:
    """Hotspots in the window ending at the latest processed case, kept if they contain a processed case."""
    if options.get("hotspots") is False or not case_dates:
        return [], []
    from datetime import date, timedelta

    from ..agents.hotspot import detect_hotspots
    days = int(options.get("hotspot_days") or HOTSPOT_WINDOW_DAYS)
    until = date.fromisoformat(max(case_dates)) + timedelta(days=1)
    since = until - timedelta(days=days)
    try:
        found = detect_hotspots(graph.deps, since=since.isoformat(), until=until.isoformat())
    except Exception as exc:  # hotspots are an extra; the link alerts stand without them
        graph.deps.tracer.emit("Hotspot detector", "hotspots_failed", output_summary=str(exc)[:300],
                               status="error")
        return [], [f"hotspots: {exc}"]
    relevant = [h for h in found if case_ids & set(h.get("crimes") or [])]
    return [_alert_view(a) | {k: a.get(k) for k in ("cell", "category", "window", "observed", "expected",
                                                    "p_value")}
            for a in graph.writer.write_hotspots(relevant)], []


def _dispatch(graph: AgentGraph, kind: str, payload: Mapping[str, Any], options: Mapping[str, Any]
              ) -> tuple[dict[str, Any], str]:
    if kind in ("case", "batch"):
        ids = [payload["crime_id"]] if kind == "case" else list(payload.get("crime_ids") or [])[:MAX_BATCH]
        if not ids:
            raise ValueError("batch input needs crime_ids")
        alerts: list[dict] = []
        struck = dropped = 0
        errors: list[str] = []
        statuses = []
        case_dates: list[str] = []
        for cid in ids:
            state = graph.run("case", {"crime_id": cid}, options)
            if (state.get("case") or {}).get("occurred_from"):
                case_dates.append(str(state["case"]["occurred_from"])[:10])
            a, s, d = _case_output(state)
            alerts += a
            struck += s
            dropped += d
            errors += state.get("errors", [])
            statuses.append(state.get("status"))
            if state.get("status") == "deadline":
                break
        status = "success" if all(s == "success" for s in statuses) and len(statuses) == len(ids) else (
            "deadline" if "deadline" in statuses else "partial")
        hotspots, herr = _hotspots(graph, case_dates, set(ids), options)
        errors += herr
        series = detect_series(alerts)  # 3+ connected cases among this run's links (LNK-05)
        return ({"alerts": alerts, "series": series, "hotspots": hotspots, "errors": errors,
                 "summary": summarise(alerts, struck, dropped, f"{len(statuses)}/{len(ids)} cases processed")},
                status)
    if kind == "tip":
        state = graph.run("tip", payload, options)
        tip = state.get("tip") or {}
        guard = tip.get("guard") or {}
        return ({"tip": {"tip_id": tip.get("tip_id"), "guard": {k: guard.get(k) for k in
                                                               ("verdict", "intent", "risk", "emergency")},
                         "features": tip.get("features")},
                 "alerts": [], "series": [], "hotspots": [],
                 "summary": f"tip {guard.get('verdict')}"}, state.get("status") or "success")
    if kind == "search":
        state = graph.run("search", payload, options)
        res = state.get("search") or {}
        return ({"search": res, "alerts": [], "series": [], "hotspots": [],
                 "summary": f"{len(res.get('results') or [])} results via {res.get('route')}"},
                state.get("status") or "success")
    raise ValueError(f"unknown input kind {kind!r}")
