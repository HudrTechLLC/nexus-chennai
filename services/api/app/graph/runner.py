"""Runs the agent graph for one request and shapes the Part H `/run` response. Task WS2-16.

Wires the real adapters (Zetaris, Nightshift), the engines facade bound to this run's
tracer, a store and the hard deadline. Sample mode uses the same graph and agent logic;
only the adapters switch to DuckDB over data/sample and recorded model fixtures (R6).
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from collections.abc import Callable, Mapping
from typing import Any

from .. import engines
from ..adapters.nightshift import NightshiftClient
from ..adapters.supabase import SupabaseClient
from ..adapters.zetaris import ZetarisClient
from ..agents import AgentDeps, DeadlineExceeded, MemoryStore, Store, detect_series
from ..agents.series import describe_series, find_test_firs, flag_test_firs, read_member_cases
from ..config import Settings
from ..tracing import Tracer, new_run_id
from .pipeline import AgentGraph
from .local_store import LocalStore, store_kind
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


class CaseNotFound(KeyError):
    """The crime_id(s) of a case run are not in the system (main.py maps this to HTTP 404)."""

    def __str__(self) -> str:
        return f"crime_id not found: {self.args[0]}"


RECORD_FLAG = "NEXUS_RECORD_FIXTURES"


def record_fixtures() -> bool:
    """Save live model replies to data/sample/model_fixtures (judge-path recording, R3/R6).

    An environment switch for whoever records the bundle, never a /run option, so a request can't
    write files. Replay needs nothing: sample mode replays when Nightshift is unreachable.
    """
    return os.environ.get(RECORD_FLAG, "").strip().lower() in ("1", "true", "on", "yes")


@contextmanager
def agent_deps(settings: Settings, run_id: str, *, zetaris: Any = None, nightshift: Any = None
               ) -> Iterator[AgentDeps]:
    """Deps for one API call outside /run (drafts, dossiers, briefings): real adapters, traced, deadline."""
    tracer = Tracer(run_id, settings.logs_dir)
    z = zetaris or ZetarisClient(settings, tracer)
    n = nightshift or NightshiftClient(settings, tracer, record_fixtures=record_fixtures())
    try:
        with engines.use_tracer(tracer):
            yield AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=engines,
                            deadline=time.monotonic() + settings.run_deadline_seconds)
    finally:
        if zetaris is None:
            z.close()
        if nightshift is None:
            n.close()


EVIDENCE_BUCKET = "evidence"  # private Storage bucket of evidence stills (D-029)


def media_loader_for(settings: Settings, client: SupabaseClient | None = None) -> Callable[[str], bytes] | None:
    """How the Extractor reads an evidence still, or None.

    Live runs with Supabase read the private evidence bucket, so the vision lane is actually attempted: if Nightshift
    refuses images (no_vision_model) the trace says `vision_unavailable` and the officer caption is used; when it
    admits them, stills are read with no code change. Sample mode never loads media, so the judge examples (whose
    fixtures have no vision calls) stay byte-stable.
    """
    if settings.sample_mode:
        return None
    sb = client or SupabaseClient(settings)
    if not sb.configured:
        return None
    return lambda path: sb.download(EVIDENCE_BUCKET, path)


def default_store(settings: Settings, tracer: Tracer) -> Store:
    """The store `store_kind` names (WS2-22): Supabase when configured, else local files in live mode and
    memory in sample mode; `NEXUS_STORE` overrides."""
    kind = store_kind(settings)
    if kind == "supabase":
        return SupabaseStore(SupabaseClient(settings), tracer)
    if kind == "local":
        return LocalStore(settings.local_store_dir)
    return MemoryStore()


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
    n = nightshift or NightshiftClient(settings, tracer, record_fixtures=record_fixtures())
    if options.get("persist") is False:
        store: Store = MemoryStore()
    else:
        store = (store_factory or default_store)(settings, tracer)
    if isinstance(store, (SupabaseStore, LocalStore)):
        store.start_run(run_id, kind, f"logs/trace-{run_id}.jsonl",
                        subject=str(payload.get("crime_id")) if kind == "case" and payload.get("crime_id") else None)
    tracer.emit("api", "run_received", input_summary=f"kind={kind}", status="ok",
                output_summary=f"sample_mode={settings.sample_mode} deadline={settings.run_deadline_seconds}s")
    status = "failed"
    try:
        with engines.use_tracer(tracer):
            deps = AgentDeps(tracer=tracer, zetaris=z, nightshift=n, engines=engines, store=store, deadline=deadline)
            graph = AgentGraph(deps, media_loader=media_loader_for(settings))
            output, status = _dispatch(graph, kind, payload, options)
    except Exception as exc:
        tracer.emit("api", "run_failed", output_summary=f"{type(exc).__name__}: {exc}"[:300], status="error")
        _finish(store, run_id, "failed", kind)
        raise
    finally:
        if zetaris is None:
            z.close()
        if nightshift is None:
            n.close()
    elapsed = round(time.perf_counter() - started, 2)
    tracer.emit("api", "run_finished", output_summary=f"{status} in {elapsed}s", status=status)
    _finish(store, run_id, status, kind)
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


def _finish(store: Store, run_id: str, status: str, kind: str) -> None:
    """Close the run (Supabase: and copy its trace); a failure here never loses the run's answer."""
    if not isinstance(store, (SupabaseStore, LocalStore)):
        return
    try:
        store.finish_run(run_id, status, kind)
    except Exception as exc:  # the JSONL trace is still on disk
        store.tracer.emit("api", "trace_copy_failed", output_summary=str(exc)[:300], status="error")


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


def _detect_series(graph: AgentGraph, alerts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Series among this run's links, without D-033 test FIRs: {crime_id: reason} of the ones left out."""
    series = detect_series(alerts)
    if not series:
        return series, {}
    try:
        rows = read_member_cases(graph.deps, [cid for s in series for cid in s["crime_ids"]]) or {}
    except DeadlineExceeded:
        # The run's alerts are already written; losing the whole run output for a late series check is worse than
        # skipping series this run (never save unchecked: a test FIR could join). The next run detects them.
        graph.deps.tracer.emit("Series analyst", "series_skipped", input_summary=f"{len(series)} series",
                               output_summary="run deadline passed before the member check; series not saved",
                               status="degraded")
        return [], {}
    excluded = flag_test_firs(rows)
    for cid, why in sorted(excluded.items()):
        graph.deps.tracer.emit("Series analyst", "series_member_excluded", input_summary=cid, output_summary=why,
                               status="ok", extra={"crime_id": cid, "reason": why})
    if excluded:
        series = detect_series(alerts, excluded=set(excluded))
    for ser in series:  # a descriptive name from the members' dominant MO (code, no model)
        name = describe_series([rows[cid] for cid in ser["crime_ids"] if cid in rows])
        if name:
            ser["name"] = name
    return series, excluded


def _save_series(graph: AgentGraph, series: list[dict[str, Any]], excluded: Mapping[str, str] | None = None
                 ) -> list[str]:
    """Persist detected series (series + series_members); the stored id replaces the hash id when a series grew.

    A stored member this run did not place in the series is removed only when it is a D-033 test FIR
    (`series_member_removed`); members a run simply did not see are kept.
    """
    errors: list[str] = []
    known = dict(excluded or {})

    def exclude(ids: list[str]) -> dict[str, str]:
        unread = [cid for cid in ids if cid not in known]
        known.update(find_test_firs(graph.deps, unread) if unread else {})
        return {cid: known[cid] for cid in ids if cid in known}

    def name_for(ids: list[str]) -> str | None:
        """The descriptive name over every member of a stored series (not just this run's), or None if unreadable."""
        try:
            rows = read_member_cases(graph.deps, ids) or {}
        except DeadlineExceeded:
            return None
        if any(cid not in rows for cid in ids):  # a partial read would name a subset again: keep the stored name
            return None
        return describe_series([rows[cid] for cid in ids])

    store = graph.deps.store
    for ser in series:
        try:
            before = len(getattr(store, "removed", []))
            ser["series_id"] = store.write_series(ser, graph.deps.tracer.run_id, exclude=exclude, name_for=name_for)
            for r in getattr(store, "removed", [])[before:]:
                graph.deps.tracer.emit("Series analyst", "series_member_removed", input_summary=r["series_id"],
                                       output_summary=f"{r['crime_id']}: {r['reason']}", status="ok", extra=dict(r))
        except Exception as exc:  # the run's answer stands without the write
            graph.deps.tracer.emit("Series analyst", "series_save_failed", input_summary=ser.get("series_id"),
                                   output_summary=str(exc)[:300], status="error")
            errors.append(f"series {ser.get('series_id')}: {exc}")
    return errors


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
        not_found: list[str] = []
        case_dates: list[str] = []
        for cid in ids:
            try:
                state = graph.run("case", {"crime_id": cid}, options)
            except DeadlineExceeded:
                raise
            except Exception as exc:
                if kind == "case":
                    raise  # a single-case /run keeps its 422/503 mapping
                # batch: record the case's failure and keep going (status ends "partial")
                graph.deps.tracer.emit("api", "case_failed", input_summary=cid,
                                       output_summary=f"{type(exc).__name__}: {exc}"[:300], status="error")
                errors.append(f"{cid}: {type(exc).__name__}: {str(exc)[:200]}")
                statuses.append("failed")
                continue
            if state.get("status") == "not_found":
                if kind == "case":
                    raise CaseNotFound(cid)
                not_found.append(cid)  # batch: listed, never counted as processed
                continue
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
        if not_found and len(not_found) == len(ids):
            raise CaseNotFound(", ".join(not_found))
        if not_found:
            errors.append(f"not found: {', '.join(not_found)}")
        processed = sum(1 for st in statuses if st != "failed")
        status = "success" if all(s == "success" for s in statuses) and len(statuses) == len(ids) else (
            "deadline" if "deadline" in statuses else "partial")
        hotspots, herr = _hotspots(graph, case_dates, set(ids), options)
        errors += herr
        series, excluded = _detect_series(graph, alerts)  # 3+ connected cases among this run's links (LNK-05)
        errors += _save_series(graph, series, excluded)
        return ({"alerts": alerts, "series": series, "hotspots": hotspots, "errors": errors,
                 "summary": summarise(alerts, struck, dropped, f"{processed}/{len(ids)} cases processed")},
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
