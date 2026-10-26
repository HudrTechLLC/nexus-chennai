"""Skeptic agent (spec E3, F1 step 6, LNK-04). Task WS2-13.

For each scored pair the Skeptic:
1. Re-queries Zetaris itself (q_case and q_features for both crimes, plus the support
   queries the factors relied on). It never reuses the Linker's rows.
2. Recomputes every factor from its own rows in code. A factor is struck when the
   Skeptic's rows don't support it: no data, or a value more than STRIKE_TOLERANCE
   below the Linker's. The pair is then rescored (app.scoring.strike), so a strike can
   only lower the score. This includes the forensic factor, so a forensic exemption
   from the coverage guard only stands when the Skeptic has confirmed the match itself
   (DECISIONS D-016).
3. Decides the verdict:
   - drop: no alert after the strikes (code; the model cannot overrule this);
   - send_back: the evidence is weak and the Planner should re-query, narrower or wider
     (the model proposes this; it is capped at 2 rounds by the graph);
   - approve: otherwise.
   The `reason` lane writes the critique and may downgrade approve to send_back or drop,
   but it can never upgrade a pair (R7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..scoring import PairScore, strike
from .base import AgentDeps, AgentError, chat_json, crime_from_row, features_from_row, short
from .linker import CORROBORATION_QUERIES, ScoredPair, compute_factors, corroboration_items, factor_payload

AGENT = "Skeptic"
STRIKE_TOLERANCE = 0.15
MAX_SEND_BACKS = 2

SKEPTIC_PROMPT = """You are the Skeptic: you challenge proposed links between crimes before analysts see them.
Numbers were computed in code and re-checked against fresh rows; you cannot change them.
For each pair decide: "approve", "send_back" (evidence is weak or the search window looks wrong:
say what the Planner should re-query, e.g. a narrower time window), or "drop" (the link is not credible).
Be strict about coincidence: same area alone is not a link.
Return ONE JSON object: {"pairs": {"<pair_id>": {"verdict": "approve"|"send_back"|"drop",
"critique": str, "requery": {"days": int|null, "ring": int|null, "note": str}|null}}}"""

VERDICT_TO_STATUS = {"approve": "approved", "send_back": "needs_revision", "drop": "rejected"}


@dataclass
class SkepticResult:
    pair: ScoredPair
    verdict: str  # approve | send_back | drop
    struck: list[str] = field(default_factory=list)
    critique: str = ""
    requery: dict[str, Any] | None = None
    rechecked: dict[str, float | None] = field(default_factory=dict)
    query_ids: list[str] = field(default_factory=list)
    round: int = 1

    def review_block(self) -> dict[str, Any]:
        """The D3.11 `skeptic` object."""
        return {"rounds": self.round, "struck": list(self.struck), "verdict": VERDICT_TO_STATUS[self.verdict]}


def factors_to_strike(linker: PairScore, rechecked: Mapping[str, float | None]) -> list[str]:
    """Factors whose fresh value is missing or clearly lower than the Linker's."""
    out = []
    for f in linker.factors:
        if f.value is None or f.struck_by_skeptic:
            continue
        fresh = rechecked.get(f.factor)
        if fresh is None or fresh < f.value - STRIKE_TOLERANCE:
            out.append(f.factor)
    return out


class Skeptic:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

    # ----- independent re-query ------------------------------------------

    def _fresh(self, sp: ScoredPair) -> tuple[dict[str, float | None], list[str]]:
        ida, idb = sp.crimes
        used = {f.factor for f in sp.score.factors if f.value is not None and not f.struck_by_skeptic}
        qids: list[str] = []

        def q(name: str, **params: Any) -> list[dict[str, Any]]:
            rows, qid = self.deps.query(name, agent=AGENT, **params)
            qids.append(qid)
            return rows

        case_a = q("q_case", crime_id=ida)
        case_b = q("q_case", crime_id=idb)
        if not case_a or not case_b:
            return {}, qids  # nothing supports anything: every factor is struck
        a, b = crime_from_row(case_a[0]), crime_from_row(case_b[0])
        feats = {r.get("crime_id"): features_from_row(r) for r in q("q_features", ids=f"{ida},{idb}")}
        fa, fb = feats.get(ida), feats.get(idb)

        anpr: list[dict[str, Any]] = []
        if "vehicle" in used:
            plates = sorted({*((fa or {}).get("entities") or {}).get("plates", []),
                             *(v.get("plate") for v in a.get("vehicles") or [] if v.get("plate"))})
            for plate in plates[:2]:
                anpr += q("q_vehicle_trail", plate_pattern=plate, t0=a.get("occurred_from"),
                          t1=b.get("occurred_from"), cells=(a.get("location") or {}).get("h3_r9") or "")

        items = None
        if "corroboration" in used:
            rows_a = {name: q(name, crime_id=ida) for name in CORROBORATION_QUERIES}
            rows_b = {name: q(name, crime_id=idb) for name in CORROBORATION_QUERIES}
            items = corroboration_items(rows_a, rows_b, ida, idb)

        persons_a = persons_b = None
        if "offender_return" in used:
            def persons(c: Mapping[str, Any], f: Mapping[str, Any] | None) -> list[dict[str, Any]]:
                mo = (f or {}).get("mo") or {}
                tags = [str(mo[k]) for k in ("approach", "target", "target_item", "escape") if mo.get(k)]
                ward = (c.get("location") or {}).get("ward")
                if not tags or ward is None:
                    return []
                return q("q_offender_return", mo_tags=",".join(tags), ward=ward, since=c.get("occurred_from"))
            persons_a, persons_b = persons(a, fa), persons(b, fb)

        fresh = compute_factors(a, b, fa, fb, anpr_rows=anpr, corroboration_items=items,
                                persons_a=persons_a, persons_b=persons_b)
        return {f.factor: f.value for f in fresh}, qids

    # ----- review ---------------------------------------------------------

    def check(self, sp: ScoredPair, round_no: int = 1) -> SkepticResult:
        """Re-query, strike, rescore. The verdict here is code-only; `review` adds the model's critique."""
        rechecked, qids = self._fresh(sp)
        to_strike = factors_to_strike(sp.score, rechecked)
        before = sp.score.score
        for name in to_strike:
            sp.score = strike(sp.score, name, memory=sp.memory)
            self.deps.tracer.emit(
                AGENT, "strike_factor", input_summary=f"pair {sp.pair_id} factor {name}",
                output_summary=f"fresh={rechecked.get(name)} linker="
                               f"{next(f.value for f in sp.score.factors if f.factor == name)}; "
                               f"score {before}→{sp.score.score}",
                target_agent="Linker", zetaris_query_ids=qids, status="needs_revision")
        verdict = "approve" if sp.score.alert else "drop"
        return SkepticResult(sp, verdict, struck=to_strike, rechecked=rechecked, query_ids=qids, round=round_no)

    def review(self, pairs: Sequence[ScoredPair], round_no: int = 1) -> list[SkepticResult]:
        results = [self.check(sp, round_no) for sp in pairs]
        live = [r for r in results if r.verdict == "approve"]
        if live:
            self._critique(live, round_no)
        for r in results:
            self.deps.tracer.emit(AGENT, r.verdict if r.verdict != "approve" else "approve",
                                  input_summary=f"pair {r.pair.pair_id} round {round_no}",
                                  output_summary=short(f"score={r.pair.score.score} struck={r.struck} "
                                                       f"{r.critique}"),
                                  target_agent={"approve": "Alert writer", "send_back": "Planner",
                                                "drop": None}[r.verdict],
                                  zetaris_query_ids=r.query_ids, confidence=r.pair.score.score,
                                  status=VERDICT_TO_STATUS[r.verdict])
        return results

    def _critique(self, results: Sequence[SkepticResult], round_no: int) -> None:
        payload = {r.pair.pair_id: {**factor_payload(r.pair), "struck_by_skeptic": r.struck,
                                    "coverage": r.pair.score.coverage, "rationale": r.pair.rationale}
                   for r in results}
        messages = [{"role": "system", "content": SKEPTIC_PROMPT},
                    {"role": "user", "content": short(payload, 24000)}]
        try:
            out, result = chat_json(self.deps, "reason", messages, agent=AGENT,
                                    purpose=f"critique {len(results)} pairs round {round_no}", temperature=0)
            answers = out.get("pairs") or {}
        except AgentError as exc:
            # No model critique: code verdicts stand (approve only what still alerts after strikes).
            self.deps.tracer.emit(AGENT, "critique_failed", output_summary=short(str(exc)), status="error")
            return
        for r in results:
            ans = answers.get(r.pair.pair_id) if isinstance(answers, Mapping) else None
            if not isinstance(ans, Mapping):
                continue
            v = ans.get("verdict")
            r.critique = str(ans.get("critique") or "")[:400]
            # The model may only downgrade: approve -> send_back / drop.
            if v == "drop":
                r.verdict = "drop"
            elif v == "send_back":
                if round_no <= MAX_SEND_BACKS:
                    r.verdict = "send_back"
                    rq = ans.get("requery") if isinstance(ans.get("requery"), Mapping) else {}
                    r.requery = {"days": rq.get("days"), "ring": rq.get("ring"),
                                 "note": str(rq.get("note") or r.critique)[:300]}
                else:
                    r.critique += " (send-back cap reached; kept as approved)"
