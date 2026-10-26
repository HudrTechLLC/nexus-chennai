"""Linker agent (spec E3, F1 steps 4-5, 7). Task WS2-11.

For a case and its candidates:
1. Code works out each F2 factor from Zetaris rows (app.scoring.factors) and records the
   evidence (view + row id) behind it.
2. H-MEM adds bounded memory adjustments (`hmem.adjust`, capped in app.scoring).
3. app.scoring.score_pair combines and bands the result.
4. The `reason` lane writes one plain-English reason per factor, plus a rationale and a
   recommended action, for the pairs that alert. It sees the rows and the numbers but
   cannot change them: anything numeric it returns is ignored (R7).

To keep the run inside its deadline, the Linker fetches pair-level support (tips, calls,
news, offender returns for the candidate) only for promising pairs, and asks for all
rationales in one batched model call.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..scoring import FactorResult, PairScore, score_pair
from ..scoring import factors as F
from .base import REASON_SUMMARY_CHARS, AgentDeps, AgentError, chat_json, short

AGENT = "Linker"

PROMISING_BASE = 0.40  # fetch extra support rows only for pairs at or above this base score
MAX_SUPPORTED_PAIRS = 12
MAX_RATIONALE_PAIRS = 8

CORROBORATION_QUERIES: Mapping[str, tuple[str, str]] = {
    # query -> (view, row-id column)
    "q_tip_corroboration": ("v_tip_corroboration", "tip_id"),
    "q_calls_near": ("v_calls_near_crime", "call_id"),
    "q_news": ("v_news_mentions", "article_id"),
}

RATIONALE_PROMPT = """You explain crime-link scores to police analysts. The numbers are already computed;
you must not change or restate different numbers. For each pair, write:
- one short reason per factor, using ONLY the rows given (cite plate, place, time, MO words);
- a one-sentence rationale;
- a recommended next action for the investigating officers.
Never mention religion, caste, community or other protected attributes.
Return ONE JSON object: {"pairs": {"<pair_id>": {"factors": {"<factor>": "<reason>"}, "rationale": str,
"recommended_action": str}}}"""


@dataclass
class Candidate:
    crime: dict[str, Any]
    features: dict[str, Any] | None = None
    query_ids: dict[str, str] = field(default_factory=dict)  # named query -> Zetaris query id that fetched it


@dataclass
class ScoredPair:
    pair_id: str
    crime_a: dict[str, Any]
    crime_b: dict[str, Any]
    features_a: dict[str, Any] | None
    features_b: dict[str, Any] | None
    score: PairScore
    memory: list[dict[str, Any]] = field(default_factory=list)
    rationale: str | None = None
    recommended_action: str | None = None
    rationale_model: str | None = None
    query_ids: list[str] = field(default_factory=list)
    revisions: int = 0
    hmem_pair: dict[str, Any] = field(default_factory=dict)

    @property
    def crimes(self) -> list[str]:
        return [self.crime_a["crime_id"], self.crime_b["crime_id"]]


def pair_id(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"{x}|{y}"


# Which named query backs each view, so every evidence item can carry its query id (G2).
VIEW_QUERY: Mapping[str, str] = {
    "v_crime_unified": "q_case",
    "v_crime_features": "q_features",
    "v_vehicle_trail": "q_vehicle_trail",
    "v_offender_return": "q_offender_return",
    "v_tip_corroboration": "q_tip_corroboration",
    "v_calls_near_crime": "q_calls_near",
    "v_news_mentions": "q_news",
    "forensics": "q_case",
}


def _evq(view: str, row: Any, query_ids: Mapping[str, str] | None = None) -> dict[str, Any]:
    ref: dict[str, Any] = {"view": view, "row": str(row)}
    q = VIEW_QUERY.get(view)
    if q:
        ref["query"] = q
        if query_ids and query_ids.get(q):
            ref["query_id"] = query_ids[q]
    return ref


def hmem_side(crime: Mapping[str, Any], features: Mapping[str, Any] | None) -> dict[str, Any]:
    """One side of an H-MEM pair: MO labels and descriptors only (no ids, places or free text)."""
    f = features or {}
    return {
        "category": crime.get("category"),
        "sub_type": crime.get("sub_type"),
        "mo": {k: v for k, v in (f.get("mo") or {}).items() if v not in (None, [], "")},
        "visual_tags": list(f.get("visual_tags") or []),
        "vehicles": [" ".join(str(v.get(k)) for k in ("colour", "make_model", "type") if v.get(k))
                     for v in crime.get("vehicles") or [] if v.get("role", "used_by_offender") == "used_by_offender"],
    }


def hmem_pair(a: Mapping[str, Any], fa: Mapping[str, Any] | None, b: Mapping[str, Any],
              fb: Mapping[str, Any] | None) -> dict[str, Any]:
    """The pair shape `hmem.adjust` / `hmem.record_decision` expect: {"a": {...}, "b": {...}}."""
    return {"a": hmem_side(a, fa), "b": hmem_side(b, fb)}


def _forensic_codes(crime: Mapping[str, Any]) -> list[str]:
    return [str(f.get("match_code")) for f in crime.get("forensics") or [] if f.get("match_code")]


MO_COSINE_FLAG = "NEXUS_MO_COSINE"


def mo_text_cosine() -> Callable[[Any, Any], float | None] | None:
    """`engines.similarity.mo_cosine` when NEXUS_MO_COSINE=1 (D-027 trial), else None = scoring's own cosine.

    Default off until the eval is run both ways (chief, 26 Oct); read per call so the eval can flip it.
    """
    if os.environ.get(MO_COSINE_FLAG, "").strip().lower() not in ("1", "true", "on", "yes"):
        return None
    from ..engines.similarity import mo_cosine
    return mo_cosine


def compute_factors(
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    fa: Mapping[str, Any] | None,
    fb: Mapping[str, Any] | None,
    *,
    anpr_rows: Sequence[Mapping[str, Any]] = (),
    corroboration_items: Sequence[Mapping[str, Any]] | None = None,
    persons_a: Sequence[Mapping[str, Any]] | None = None,
    persons_b: Sequence[Mapping[str, Any]] | None = None,
    query_ids: Mapping[str, str] | None = None,
) -> list[FactorResult]:
    """All nine F2 factors for one pair, each with its evidence rows. Pure code.

    `query_ids` maps named query -> Zetaris query id, so evidence items cite their query.
    """
    ida, idb = a["crime_id"], b["crime_id"]

    def _ev(view: str, row: Any) -> dict[str, Any]:  # noqa: F811 - binds query_ids
        return _evq(view, row, query_ids)

    crimes_ev = [_ev("v_crime_unified", ida), _ev("v_crime_unified", idb)]
    feats_ev = [_ev("v_crime_features", ida), _ev("v_crime_features", idb)]
    out = [
        FactorResult("mo_similarity", F.mo_similarity(fa, fb, text_cosine=mo_text_cosine()), evidence=feats_ev),
        FactorResult("space_time", F.space_time(a, b), evidence=crimes_ev),
    ]
    trail = [r for r in anpr_rows if r.get("crime_id") in (ida, idb)]
    out.append(FactorResult("vehicle", F.vehicle(a, b, trail),
                            evidence=crimes_ev + [_ev("v_vehicle_trail", r.get("read_id")) for r in trail]))
    out.append(FactorResult("suspect_description",
                            F.suspect_description(a.get("offenders_described"), b.get("offenders_described")),
                            evidence=crimes_ev))
    out.append(FactorResult("weapon_tool", F.weapon_tool(a, b), evidence=crimes_ev))
    out.append(FactorResult("target_profile", F.target_profile(fa, fb), evidence=feats_ev))
    out.append(FactorResult("forensic", F.forensic(_forensic_codes(a), _forensic_codes(b)),
                            evidence=[_ev("forensics", f.get("forensic_id") or f.get("match_code"))
                                      for f in [*(a.get("forensics") or []), *(b.get("forensics") or [])]]))
    items = list(corroboration_items or [])
    out.append(FactorResult("corroboration", F.corroboration(items, ida, idb),
                            evidence=[_ev(it["view"], it["id"]) for it in items
                                      if {ida, idb} <= set(it.get("crime_ids") or [])]))
    out.append(FactorResult("offender_return", F.offender_return(persons_a, persons_b),
                            evidence=[_ev("v_offender_return", p.get("person_ref"))
                                      for p in persons_a or [] if p.get("person_ref") in
                                      {q.get("person_ref") for q in persons_b or []}]))
    return out


def corroboration_items(rows_a: Mapping[str, Sequence[Mapping[str, Any]]],
                        rows_b: Mapping[str, Sequence[Mapping[str, Any]]],
                        ida: str, idb: str) -> list[dict[str, Any]]:
    """Items (tips, calls, news) whose row id appears in both crimes' corroboration rows."""
    items = []
    for q, (view, col) in CORROBORATION_QUERIES.items():
        ids_a = {r.get(col) for r in rows_a.get(q, []) if r.get(col)}
        ids_b = {r.get(col) for r in rows_b.get(q, []) if r.get(col)}
        for rid in sorted(ids_a & ids_b, key=str):
            items.append({"view": view, "id": rid, "crime_ids": [ida, idb]})
    return items


def described(c: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Suspect descriptions for a prompt: allow-listed keys only (LNK-13). Gender, complexion or any other
    protected attribute an FIR might carry never reaches the model; key order is kept, so prompts are stable."""
    return [{k: v for k, v in d.items() if k in F.SUSPECT_ALLOWED_KEYS}
            for d in c.get("offenders_described") or [] if isinstance(d, Mapping)]


def factor_payload(sp: ScoredPair) -> dict[str, Any]:
    """What the reason lane sees for one pair: numbers + the rows behind them."""
    def crime_facts(c: Mapping[str, Any], f: Mapping[str, Any] | None) -> dict[str, Any]:
        return {
            "crime_id": c.get("crime_id"), "station": c.get("station_id"), "category": c.get("sub_type") or
            c.get("category"), "when": c.get("occurred_from"), "where": (c.get("location") or {}).get("address"),
            "vehicles": c.get("vehicles"), "described": described(c), "weapon": c.get("weapon"),
            "mo": (f or {}).get("mo"), "visual_tags": (f or {}).get("visual_tags"),
        }
    km = F.distance_km(sp.crime_a, sp.crime_b)
    days = F.days_apart(sp.crime_a, sp.crime_b)
    return {
        "a": crime_facts(sp.crime_a, sp.features_a),
        "b": crime_facts(sp.crime_b, sp.features_b),
        "distance_km": None if km is None else round(km, 1),
        "days_apart": None if days is None else round(days, 1),
        # Only {view, row}: query ids are fresh uuids per call and would make every prompt unique,
        # so recorded fixtures could never replay in sample mode (R6).
        "factors": [{"factor": f.factor, "value": None if f.value is None else round(f.value, 2),
                     "evidence": [{"view": e["view"], "row": e["row"]} for e in f.evidence[:6]]}
                    for f in sp.score.factors if f.value is not None],
        "score": sp.score.score,
        "band": sp.score.band,
    }


def fallback_reason(f: FactorResult) -> str:
    rows = ", ".join(e["row"] for e in f.evidence[:3])
    return f"{f.factor.replace('_', ' ')} computed in code from {rows or 'case rows'} (model gave no reason)"


class Linker:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    # ----- memory -------------------------------------------------------

    def _memory(self, pid: str, pair: dict[str, Any]) -> list[dict[str, Any]]:
        hmem = getattr(self.deps.engines, "hmem", None)
        if hmem is None:
            return []
        try:
            adj = hmem.adjust(pair)
        except Exception as exc:
            self.deps.tracer.emit(AGENT, "memory_failed", input_summary=pid, output_summary=short(str(exc)),
                                  engine="hmem", status="error")
            return []
        if not adj or not adj.get("delta"):
            return []
        self.deps.tracer.emit(AGENT, "memory_applied", input_summary=pid, output_summary=short(adj),
                              engine="hmem", status="ok")
        return [adj]

    # ----- support rows for one candidate --------------------------------

    def _candidate_support(self, b: Mapping[str, Any], fb: Mapping[str, Any] | None
                           ) -> tuple[dict[str, list], list | None, dict[str, str]]:
        rows: dict[str, list] = {}
        qids: dict[str, str] = {}
        for q in CORROBORATION_QUERIES:
            try:
                rows[q], qids[q] = self.deps.query(q, agent=AGENT, crime_id=b["crime_id"])
            except Exception as exc:
                self.deps.tracer.emit(AGENT, "support_failed", input_summary=f"{q} {b['crime_id']}",
                                      output_summary=short(str(exc)), status="error")
        persons = None
        mo = (fb or {}).get("mo") or {}
        tags = [str(mo[k]) for k in ("approach", "target", "target_item", "escape") if mo.get(k)]
        ward = (b.get("location") or {}).get("ward")
        if tags and ward is not None:
            try:
                persons, qids["q_offender_return"] = self.deps.query(
                    "q_offender_return", agent=AGENT, mo_tags=",".join(tags), ward=ward, since=b.get("occurred_from"))
            except Exception as exc:
                self.deps.tracer.emit(AGENT, "support_failed", input_summary=f"q_offender_return {b['crime_id']}",
                                      output_summary=short(str(exc)), status="error")
        return rows, persons, qids

    # ----- scoring --------------------------------------------------------

    def score(self, case: Mapping[str, Any], features: Mapping[str, Any] | None, candidates: Sequence[Candidate],
              support: Mapping[str, Mapping[str, Any]], case_query_ids: Mapping[str, str] | None = None
              ) -> list[ScoredPair]:
        """Score every candidate pair in code. `support` is the Planner's executed plan."""
        anpr = list((support.get("q_vehicle_trail") or {}).get("rows") or [])
        case_rows = {q: list((support.get(q) or {}).get("rows") or []) for q in CORROBORATION_QUERIES}
        persons_a = (support.get("q_offender_return") or {}).get("rows")
        plan_qmap = {name: v["query_id"] for name, v in support.items() if v.get("query_id")}
        plan_qmap.update(case_query_ids or {})

        # Pass 1: base factors without pair-level support.
        prelim: list[tuple[Candidate, list[FactorResult], PairScore]] = []
        for cand in candidates:
            if cand.crime.get("crime_id") == case["crime_id"]:
                continue
            fs = compute_factors(case, cand.crime, features, cand.features, anpr_rows=anpr,
                                 query_ids={**plan_qmap, **cand.query_ids})
            prelim.append((cand, fs, score_pair(fs)))
        prelim.sort(key=lambda t: t[2].base_score or 0.0, reverse=True)

        pairs: list[ScoredPair] = []
        for i, (cand, fs, base) in enumerate(prelim):
            self.deps.check_deadline(AGENT)
            b, fb = cand.crime, cand.features
            qmap = {**plan_qmap, **cand.query_ids}
            if (base.base_score or 0.0) >= PROMISING_BASE and i < MAX_SUPPORTED_PAIRS:
                rows_b, persons_b, more = self._candidate_support(b, fb)
                qmap.update(more)
                fs = compute_factors(case, b, features, fb, anpr_rows=anpr,
                                     corroboration_items=corroboration_items(case_rows, rows_b, case["crime_id"],
                                                                             b["crime_id"]),
                                     persons_a=persons_a, persons_b=persons_b, query_ids=qmap)
            pid = pair_id(case["crime_id"], b["crime_id"])
            hp = hmem_pair(case, features, b, fb)
            memory = self._memory(pid, hp)
            ps = score_pair(fs, memory=memory)
            qids = list(dict.fromkeys(qmap.values()))
            sp = ScoredPair(pid, dict(case), dict(b), dict(features) if features else None,
                            dict(fb) if fb else None, ps, memory, query_ids=qids, hmem_pair=hp)
            pairs.append(sp)
            self.deps.tracer.emit(AGENT, "score_pair", input_summary=sp.pair_id,
                                  output_summary=f"score={ps.score} band={ps.band} coverage={ps.coverage}",
                                  zetaris_query_ids=qids[-6:], confidence=ps.score, status="ok")
        pairs.sort(key=lambda p: p.score.score or 0.0, reverse=True)
        return pairs

    def rescore(self, sp: ScoredPair, factors: Sequence[FactorResult]) -> ScoredPair:
        """Recompute a pair from revised factors (after a Skeptic send-back). Memory is reapplied."""
        sp.score = score_pair(factors, memory=sp.memory)
        sp.revisions += 1
        self.deps.tracer.emit(AGENT, "rescore_pair", input_summary=sp.pair_id,
                              output_summary=f"score={sp.score.score} band={sp.score.band} rev={sp.revisions}",
                              status="ok")
        return sp

    # ----- explanation ----------------------------------------------------

    def explain(self, pairs: Sequence[ScoredPair]) -> None:
        """Ask the reason lane for factor reasons + rationale for alerting pairs (one batched call)."""
        todo = [p for p in pairs if p.score.alert][:MAX_RATIONALE_PAIRS]
        if not todo:
            return
        payload = {p.pair_id: factor_payload(p) for p in todo}
        messages = [{"role": "system", "content": RATIONALE_PROMPT},
                    {"role": "user", "content": short(payload, 24000)}]
        model = None
        try:
            out, result = chat_json(self.deps, "reason", messages, agent=AGENT,
                                    purpose=f"rationale {len(todo)} pairs", temperature=0.2, expect="pairs")
            model = result.model
            answers = out.get("pairs") or {}
        except AgentError as exc:
            self.deps.tracer.emit(AGENT, "rationale_failed", input_summary=f"{len(todo)} pairs",
                                  output_summary=short(f"code reasons used for every pair: {exc}"), status="degraded")
            answers = {}
        for p in todo:
            ans = answers.get(p.pair_id) if isinstance(answers, Mapping) else None
            ans = ans if isinstance(ans, Mapping) else {}
            reasons = ans.get("factors") if isinstance(ans.get("factors"), Mapping) else {}
            for f in p.score.factors:
                if f.value is None:
                    continue
                text = reasons.get(f.factor)
                f.reason = str(text).strip()[:400] if isinstance(text, str) and text.strip() else fallback_reason(f)
            p.rationale = str(ans.get("rationale") or "").strip()[:600] or None
            p.recommended_action = str(ans.get("recommended_action") or "").strip()[:400] or None
            p.rationale_model = model
            self.deps.tracer.emit(AGENT, "explain_pair", input_summary=p.pair_id,
                                  output_summary=short(p.rationale or "(no rationale)", REASON_SUMMARY_CHARS), model=model,
                                  target_agent="Skeptic", status="ok" if p.rationale else "fallback")
