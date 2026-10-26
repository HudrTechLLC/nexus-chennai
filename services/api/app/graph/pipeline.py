"""The agent graph (spec C4) as a LangGraph StateGraph. Tasks WS2-09, WS2-16.

    router ─┬─ tip ──> tip_guard ──(clean)──> tip_extract ──> END
            │                     └(quarantine)──────────────> END
            ├─ search ─> search ──────────────────────────────> END
            └─ case ──> load_case ─> extract ─> plan ─> link ─> skeptic ─┬─(send back)─> plan
                                                                          └──────────────> write ─> END

Caps (C4): Planner at most 3 query rounds; Skeptic -> Planner send-backs at most 2 per
run; a hard run deadline (5 min by default, settings.run_deadline_seconds). When less than
MODEL_RESERVE_SECONDS remain, the reason-lane rationale and critique calls are skipped and
the code results stand. If the deadline passes, only pairs the Skeptic already approved are
written. Every step is traced.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..agents import (
    AgentDeps,
    AgentError,
    AlertWriter,
    Candidate,
    DeadlineExceeded,
    Extractor,
    Linker,
    Planner,
    ScoredPair,
    Skeptic,
    SkepticResult,
    TipGuard,
)
from ..agents.base import crime_from_row, features_from_row, short

MAX_PLAN_ROUNDS = 3
MAX_SEND_BACKS = 2
MAX_CANDIDATES = 25
MODEL_RESERVE_SECONDS = 45.0


class RunState(TypedDict, total=False):
    kind: str
    payload: dict[str, Any]
    options: dict[str, Any]
    route: str
    status: str
    errors: list[str]
    # case path
    case: dict[str, Any]
    case_query_ids: dict[str, str]
    features: dict[str, Any] | None
    context: dict[str, Any] | None
    plan_round: int
    send_backs: int
    feedback: str | None
    requery: dict[str, Any] | None
    support: dict[str, Any]
    candidates: list[Candidate]
    to_review: list[ScoredPair]
    approved: list[SkepticResult]
    dropped: list[SkepticResult]
    pending: list[SkepticResult]
    alerts: list[dict[str, Any]]
    # tip / search paths
    tip: dict[str, Any]
    search: dict[str, Any]


def _remaining(deps: AgentDeps) -> float:
    return float("inf") if deps.deadline is None else deps.deadline - time.monotonic()


class AgentGraph:
    """Builds and runs the C4 graph for one run (one `AgentDeps`)."""

    def __init__(self, deps: AgentDeps, media_loader=None) -> None:
        self.deps = deps
        self.extractor = Extractor(deps, media_loader=media_loader)
        self.tip_guard = TipGuard(deps)
        self.planner = Planner(deps)
        self.linker = Linker(deps)
        self.skeptic = Skeptic(deps)
        self.writer = AlertWriter(deps)
        self.graph = self._build()

    # ----- helpers --------------------------------------------------------

    def _trace(self, agent: str, action: str, **kw: Any) -> None:
        self.deps.tracer.emit(agent, action, **kw)

    def _model_time(self) -> bool:
        ok = _remaining(self.deps) > MODEL_RESERVE_SECONDS
        if not ok:
            self._trace("Graph", "skip_model_for_deadline", status="degraded",
                        output_summary=f"{_remaining(self.deps):.0f}s left < {MODEL_RESERVE_SECONDS:.0f}s reserve")
        return ok

    def _deadline(self, state: RunState, where: str) -> dict[str, Any]:
        return {"status": "deadline", "errors": [*state.get("errors", []), f"deadline passed in {where}"]}

    # ----- router -----------------------------------------------------------

    def router(self, state: RunState) -> dict[str, Any]:
        kind = state["kind"]
        route = {"case": "case", "tip": "tip", "search": "search"}.get(kind)
        if route is None:
            raise ValueError(f"unknown input kind {kind!r}")
        self._trace("Scout Intent", "route", input_summary=f"kind={kind}", output_summary=f"route={route}",
                    target_agent={"case": "Extractor", "tip": "Tip Guard", "search": "Search tools"}[route],
                    status="ok")
        return {"route": route, "status": "running", "errors": [], "approved": [], "dropped": [], "pending": [],
                "alerts": [], "plan_round": 0, "send_backs": 0}

    # ----- tip path -------------------------------------------------------------

    def tip_guard_node(self, state: RunState) -> dict[str, Any]:
        screened = self.tip_guard.screen(state["payload"].get("tip") or state["payload"])
        return {"tip": screened}

    def tip_extract(self, state: RunState) -> dict[str, Any]:
        tip = state["tip"]
        try:
            feats = self.extractor.extract_tip(tip)
        except AgentError as exc:
            return {"status": "partial", "errors": [*state.get("errors", []), str(exc)]}
        return {"tip": {**tip, "features": feats}, "status": "success"}

    # ----- search path ------------------------------------------------------------

    def search_node(self, state: RunState) -> dict[str, Any]:
        q = str(state["payload"].get("q") or "")
        scout = getattr(self.deps.engines, "scout_intent", None)
        cls = scout.classify(q, "query") if scout else {"route": "entity", "intent": "entity_lookup",
                                                       "action": "clean", "risk": []}
        if cls.get("action") == "quarantine":
            self._trace("Scout Intent", "quarantine_query", input_summary=short(q, 80), status="quarantined")
            return {"search": {"route": "quarantine", "intent": cls.get("intent"), "results": []},
                    "status": "success"}
        filters = dict(state["payload"].get("filters") or {})
        try:
            rows, qid = self.deps.query("q_search", agent="Search tools", route=cls["route"], q=q,
                                        **{k: v for k, v in filters.items() if isinstance(v, (str, int, float))})
        except Exception as exc:
            return {"search": {"route": cls["route"], "intent": cls.get("intent"), "results": []},
                    "status": "partial", "errors": [str(exc)]}
        return {"search": {"route": cls["route"], "intent": cls.get("intent"), "results": rows, "query_id": qid},
                "status": "success"}

    # ----- case path ----------------------------------------------------------------

    def load_case(self, state: RunState) -> dict[str, Any]:
        cid = state["payload"]["crime_id"]
        try:
            rows, qid = self.deps.query("q_case", agent="Extractor", crime_id=cid)
            if not rows:
                return {"status": "error", "errors": [f"case {cid} not found"]}
            frows, fqid = self.deps.query("q_features", agent="Extractor", ids=cid)
        except DeadlineExceeded:
            return self._deadline(state, "load_case")
        feats = features_from_row(frows[0]) if frows else None
        if feats and not any(v not in (None, [], "") for v in (feats.get("mo") or {}).values()):
            feats = None
        return {"case": crime_from_row(rows[0]), "features": feats,
                "case_query_ids": {"q_case": qid, "q_features": fqid}}

    def extract(self, state: RunState) -> dict[str, Any]:
        force = bool(state.get("options", {}).get("force_extract"))
        if state.get("features") and not force:
            self._trace("Extractor", "features_reused", input_summary=state["case"]["crime_id"], status="ok")
            return {}
        try:
            feats = self.extractor.extract_case(state["case"])
        except DeadlineExceeded:
            return self._deadline(state, "Extractor")
        except AgentError as exc:
            # Linking still runs on the structured FIR fields; MO-based factors stay empty.
            return {"features": None, "errors": [*state.get("errors", []), str(exc)]}
        wm = getattr(self.deps.engines, "world_model", None)
        ctx = None
        if wm is not None:
            try:
                ctx = wm.context([state["case"]["crime_id"]])
            except Exception as exc:
                self._trace("Planner", "context_failed", output_summary=short(str(exc)), engine="world_model",
                            status="error")
        return {"features": feats, "context": ctx}

    def _fetch_candidates(self, rows: list[dict[str, Any]], exclude: str) -> list[Candidate]:
        def nearness(r: Mapping[str, Any]) -> float:
            # q_candidates gives km_apart / days_apart; closest first (space_time's own scales).
            try:
                return float(r.get("km_apart") or 0) / 3.0 + float(r.get("days_apart") or 0) / 14.0
            except (TypeError, ValueError):
                return 0.0
        rows = sorted(rows, key=nearness)
        ids = [r["crime_id"] for r in rows if r.get("crime_id") and r["crime_id"] != exclude]
        ids = list(dict.fromkeys(ids))[:MAX_CANDIDATES]
        if not ids:
            return []
        frows, fqid = self.deps.query("q_features", agent="Planner", ids=",".join(ids))
        feats = {r.get("crime_id"): features_from_row(r) for r in frows}
        out = []
        for cid in ids:
            try:
                crows, cqid = self.deps.query("q_case", agent="Planner", crime_id=cid)
            except DeadlineExceeded:
                raise
            except Exception as exc:  # one unreadable candidate must not lose the case's other links
                self.deps.tracer.emit("Planner", "candidate_failed", input_summary=cid,
                                      output_summary=str(exc)[:300], status="error")
                continue
            if crows:
                out.append(Candidate(crime_from_row(crows[0]), feats.get(cid),
                                     query_ids={"q_case": cqid, "q_features": fqid}))
        return out

    def plan(self, state: RunState) -> dict[str, Any]:
        rnd = state.get("plan_round", 0) + 1
        case, feats = state["case"], state.get("features")
        try:
            plan = self.planner.plan(case, feats, round_no=rnd, feedback=state.get("feedback"),
                                     context=state.get("context")) if self._model_time() else None
            if plan is None:
                from ..agents.planner import Plan, default_plan
                plan = Plan(default_plan(case, feats), rnd, "default", ["deadline reserve"])
            rq = state.get("requery") or {}
            for step in plan.steps:  # Skeptic's narrower/wider request wins over the model's numbers
                if step.name == "q_candidates":
                    for k in ("days", "ring"):
                        if rq.get(k) is not None:
                            step.params[k] = int(rq[k])
            support = self.planner.execute(plan)
            cands = self._fetch_candidates(support.get("q_candidates", {}).get("rows", []), case["crime_id"])
        except DeadlineExceeded:
            return {**self._deadline(state, "Planner"), "plan_round": rnd}
        return {"plan_round": rnd, "support": support, "candidates": cands}

    def link(self, state: RunState) -> dict[str, Any]:
        cands = state.get("candidates", [])
        pending = state.get("pending") or []
        if pending:  # a send-back round re-scores only the pairs the Skeptic sent back
            wanted = {r.pair.crime_b["crime_id"] for r in pending}
            cands = [c for c in cands if c.crime["crime_id"] in wanted] or [
                Candidate(r.pair.crime_b, r.pair.features_b) for r in pending]
        try:
            pairs = self.linker.score(state["case"], state.get("features"), cands, state.get("support", {}),
                                      case_query_ids=state.get("case_query_ids"))
            alerting = [p for p in pairs if p.score.alert]
            if alerting and self._model_time():
                self.linker.explain(alerting)
        except DeadlineExceeded:
            return self._deadline(state, "Linker")
        return {"to_review": alerting, "pending": []}

    def skeptic_node(self, state: RunState) -> dict[str, Any]:
        rnd = state.get("send_backs", 0) + 1
        try:
            results = self.skeptic.review(state.get("to_review", []), round_no=rnd, critique=self._model_time())
        except DeadlineExceeded:
            return self._deadline(state, "Skeptic")
        approved = [*state.get("approved", []), *(r for r in results if r.verdict == "approve")]
        dropped = [*state.get("dropped", []), *(r for r in results if r.verdict == "drop")]
        sent = [r for r in results if r.verdict == "send_back"]
        update: dict[str, Any] = {"approved": approved, "dropped": dropped, "to_review": []}
        if sent and self._can_send_back(state):
            update.update(pending=sent, send_backs=rnd,
                          feedback="; ".join(f"{r.pair.pair_id}: {r.critique}" for r in sent)[:1500],
                          requery=next((r.requery for r in sent if r.requery), None))
        else:
            # Caps or deadline reached: a sent-back pair that still alerts stands as approved.
            for r in sent:
                r.verdict = "approve" if r.pair.score.alert else "drop"
                r.critique += " (revision cap reached)"
            update["approved"] = [*approved, *(r for r in sent if r.verdict == "approve")]
            update["dropped"] = [*dropped, *(r for r in sent if r.verdict == "drop")]
            update["pending"] = []
        return update

    def _can_send_back(self, state: RunState) -> bool:
        return (state.get("send_backs", 0) < MAX_SEND_BACKS and state.get("plan_round", 0) < MAX_PLAN_ROUNDS
                and _remaining(self.deps) > MODEL_RESERVE_SECONDS)

    def write(self, state: RunState) -> dict[str, Any]:
        alerts = self.writer.write(state.get("approved", []))
        status = state.get("status")
        return {"alerts": alerts, "status": status if status in ("deadline", "error") else "success"}

    # ----- edges ------------------------------------------------------------------------

    @staticmethod
    def _after_router(state: RunState) -> str:
        return state["route"]

    @staticmethod
    def _after_tip_guard(state: RunState) -> str:
        return "extract" if TipGuard.passes(state["tip"]) else "stop"

    @staticmethod
    def _ok(state: RunState) -> str:
        return "stop" if state.get("status") in ("deadline", "error") else "next"

    @staticmethod
    def _after_skeptic(state: RunState) -> str:
        if state.get("status") == "deadline":
            return "write"
        return "plan" if state.get("pending") else "write"

    def _build(self):
        g = StateGraph(RunState)
        g.add_node("router", self.router)
        g.add_node("tip_guard", self.tip_guard_node)
        g.add_node("tip_extract", self.tip_extract)
        g.add_node("search", self.search_node)
        g.add_node("load_case", self.load_case)
        g.add_node("extract", self.extract)
        g.add_node("plan", self.plan)
        g.add_node("link", self.link)
        g.add_node("skeptic", self.skeptic_node)
        g.add_node("write", self.write)

        g.add_edge(START, "router")
        g.add_conditional_edges("router", self._after_router, {"tip": "tip_guard", "search": "search",
                                                               "case": "load_case"})
        g.add_conditional_edges("tip_guard", self._after_tip_guard, {"extract": "tip_extract", "stop": END})
        g.add_edge("tip_extract", END)
        g.add_edge("search", END)
        g.add_conditional_edges("load_case", self._ok, {"next": "extract", "stop": END})
        g.add_conditional_edges("extract", self._ok, {"next": "plan", "stop": "write"})
        g.add_conditional_edges("plan", self._ok, {"next": "link", "stop": "write"})
        g.add_conditional_edges("link", self._ok, {"next": "skeptic", "stop": "write"})
        g.add_conditional_edges("skeptic", self._after_skeptic, {"plan": "plan", "write": "write"})
        g.add_edge("write", END)
        return g.compile()

    # ----- run ----------------------------------------------------------------------------

    def run(self, kind: str, payload: Mapping[str, Any], options: Mapping[str, Any] | None = None) -> RunState:
        # Each plan->link->skeptic loop is 3 steps; leave generous room above the caps.
        return self.graph.invoke({"kind": kind, "payload": dict(payload), "options": dict(options or {})},
                                 {"recursion_limit": 60})
