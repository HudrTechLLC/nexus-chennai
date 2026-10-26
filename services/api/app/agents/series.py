"""Series analyst (spec E3, F1 step 8, LNK-05, LNK-12).

- `detect_series` groups connected, non-rejected pair alerts into series of 3 or more
  cases. This is code: the analyst cannot approve alerts, it only groups them.
- `SeriesAnalyst.dossier` reads every case, statement, evidence tag and clean tip of a
  series through Zetaris and runs the Markovian engine over them in bounded chunks. The
  `reason` lane writes each chunk's notes. If a step's model call fails, that step uses the
  engine's extractive generator, and the trace says so. Citations are checked by the
  engine: only real record ids survive.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..engines.markovian import resolve_config
from .base import AgentDeps, AgentError, DeadlineExceeded, crime_from_row, features_from_row, short

AGENT = "Series analyst"
MIN_SERIES = 3

# Live (SER-B687C36CFC): 32 records fit the engine's default 4,000-token chunk, and Ultra's thinking ran out the
# 2,048-token reply before any notes. Small chunks keep each call short and make the Markovian chaining real;
# chunk notes are written with thinking off (measured: 508 tokens / 18 s for 11 records, cited, finished).
DOSSIER_CONFIG = resolve_config(chunk_size=2800, max_chunks=24, carryover_tokens=400)  # 800 tokens of records
DOSSIER_CHUNK_TOKENS = 2048
_CITED = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_./:-]*)\]")

CHUNK_PROMPT = """You are building a crime-series dossier for police analysts, one chunk of records at a time.
Records (each starts with its [id]):
{records}

What you have learned so far (carryover state):
{carryover}

Write concise notes on this chunk: timeline points, consistent MO, open leads. Every line of notes ends with the [id]s
it rests on, using ONLY the ids shown above. Never mention religion, caste or community. {final}
Then write the line [STATE_CHECKPOINT] followed by an updated state of at most 6 lines:
COMPLETED: read N of {total} records
REMAINING: ...
DECISIONS: recurring MO ...
CONTEXT: open leads ..."""


def chunk_problem(text: str, result: Any, chunk_ids: set[str]) -> str | None:
    """Why a chunk reply cannot be used as notes, or None. Live, a reply that was only the model's thinking
    restated the [STATE_CHECKPOINT] instruction and was cut off before any notes."""
    finish = ((getattr(result, "raw", None) or {}).get("choices") or [{}])[0].get("finish_reason")
    if finish == "length":
        return "reply cut off at max_tokens"
    if "[STATE_CHECKPOINT]" not in text:
        return "no state checkpoint"
    notes = text.rsplit("[STATE_CHECKPOINT]", 1)[0]
    if not chunk_ids & set(_CITED.findall(notes)):
        return "notes cite none of this chunk's records"
    return None


def series_id_for(crime_ids: Sequence[str]) -> str:
    return "SER-" + hashlib.sha1("|".join(sorted(crime_ids)).encode("utf-8")).hexdigest()[:10].upper()


def detect_series(alerts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Connected components of 3+ cases over pair alerts that are not rejected."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = [a for a in alerts if a.get("kind", "pair") == "pair" and a.get("status") != "rejected"
             and len(a.get("crimes") or []) == 2]
    for a in edges:
        x, y = a["crimes"]
        parent[find(x)] = find(y)
    groups: dict[str, set[str]] = {}
    for x in list(parent):
        groups.setdefault(find(x), set()).add(x)
    out = []
    for members in groups.values():
        if len(members) < MIN_SERIES:
            continue
        ids = sorted(members)
        links = [a for a in edges if set(a["crimes"]) <= members]
        out.append({
            "series_id": series_id_for(ids),
            "kind": "series",
            "crime_ids": ids,
            "stations": sorted({s for a in links for s in a.get("stations") or []}),
            "alert_ids": sorted(a.get("alert_id") for a in links if a.get("alert_id")),
            "min_score": round(min(a.get("score") or 0 for a in links), 4) if links else None,
            "status": "candidate",
        })
    return sorted(out, key=lambda s: -len(s["crime_ids"]))


DOSSIER_FIELDS = ("text", "cited_ids", "chunks", "tokens_projected", "tokens_actual", "model", "receipt_id")


def dossier_record(out: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    """The shape stored in series.dossier (agreed with nexus-6 for the WS3-11 pages)."""
    from datetime import datetime

    from ..tracing import IST
    return {**{k: out.get(k) for k in DOSSIER_FIELDS}, "receipt_ids": list(out.get("receipt_ids") or []),
            "record_count": out.get("record_count"), "run_id": run_id,
            "generated_at": datetime.now(IST).isoformat(timespec="seconds")}


class SeriesAnalyst:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps
        self.receipts: list[tuple[str, str]] = []  # (model, receipt_id) per chunk the model wrote

    def records(self, crime_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Every case, statement, evidence tag and clean tip of the series, read through Zetaris (R1)."""
        recs: list[dict[str, Any]] = []
        frows, _ = self.deps.query("q_features", agent=AGENT, ids=",".join(crime_ids))
        feats = {r.get("crime_id"): features_from_row(r) for r in frows}
        for cid in crime_ids:
            rows, _ = self.deps.query("q_case", agent=AGENT, crime_id=cid)
            if not rows:
                continue
            c = crime_from_row(rows[0])
            mo = (feats.get(cid) or {}).get("mo") or {}
            recs.append({"id": cid, "kind": "crime", "date": c.get("occurred_from"),
                         "text": c.get("narrative") or c.get("sub_type") or "",
                         "mo_tags": [str(v) for v in mo.values() if isinstance(v, str)]})
            for st in c.get("statements") or []:
                if st.get("statement_id") and st.get("text"):
                    recs.append({"id": st["statement_id"], "kind": "witness", "date": st.get("recorded_at"),
                                 "text": st["text"]})
            for ev in c.get("evidence") or []:
                tags = (ev.get("vision") or {}).get("tags")
                if ev.get("evidence_id") and tags:
                    recs.append({"id": ev["evidence_id"], "kind": "evidence", "date": ev.get("captured_at"),
                                 "text": ", ".join(tags)})
            try:
                tips, _ = self.deps.query("q_tip_corroboration", agent=AGENT, crime_id=cid)
            except DeadlineExceeded:
                raise
            except Exception as exc:  # tips enrich a dossier; without them it is still a dossier
                self.deps.tracer.emit(AGENT, "tips_unavailable", input_summary=cid, output_summary=short(str(exc)),
                                      status="degraded")
                tips = []
            for t in tips:  # Tip-Guard-clean tips only (E5); tips_v carries the vocabulary summary, never raw text
                body = t.get("summary") or t.get("text")
                if t.get("tip_id") and body:
                    recs.append({"id": t["tip_id"], "kind": "tip", "date": t.get("received_week") or t.get("received_at"),
                                 "text": body})
        seen: set[str] = set()
        unique = []
        for r in sorted(recs, key=lambda r: str(r.get("date") or "")):
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)
        return unique

    def _generator(self, total: int):
        from ..engines.markovian import make_sample_generator  # the engine's extractive generator
        fallback = make_sample_generator(total)
        progress = {"read": 0}

        def generate(prompt: str, batch: list[dict], carryover: str, step: int) -> str:
            progress["read"] += len(batch)
            last = progress["read"] >= total
            final = "This is the last chunk: write [TASK_COMPLETE] after your notes." if last else ""
            content = CHUNK_PROMPT.format(records=prompt, carryover=carryover or "(none yet)", total=total,
                                          final=final)
            ids = {str(r["id"]) for r in batch}
            try:
                budget = DOSSIER_CHUNK_TOKENS
                for attempt in (1, 2):
                    self.deps.check_deadline(AGENT)
                    res = self.deps.nightshift.chat(
                        "reason", [{"role": "user", "content": content}], agent=AGENT,
                        purpose=f"dossier chunk {step}" + (" retry" if attempt == 2 else ""), max_tokens=budget,
                        temperature=0.2, chat_template_kwargs={"enable_thinking": False})
                    text = res.content or ""
                    problem = chunk_problem(text, res, ids)
                    if problem is None:
                        self.receipts.append((res.model, res.receipt_id))
                        return text
                    self.deps.tracer.emit(AGENT, "chunk_rejected", input_summary=f"chunk {step} attempt {attempt}",
                                          output_summary=problem, engine="markovian", status="retry")
                    budget *= 2
                raise AgentError(f"chunk notes rejected twice: {problem}")
            except Exception as exc:
                self.deps.tracer.emit(AGENT, "chunk_fallback", input_summary=f"chunk {step}",
                                      output_summary=short(str(exc)), engine="markovian", status="degraded")
                return fallback(prompt, batch, carryover, step)

        return generate

    def dossier(self, series_id: str, crime_ids: Sequence[str], use_model: bool = True) -> dict[str, Any]:
        self.receipts = []
        recs = self.records(crime_ids)
        if not recs:
            raise AgentError(f"series {series_id}: no records found")
        markovian = self.deps.engines.markovian
        gen = self._generator(len(recs)) if use_model else None
        out = (markovian.dossier(series_id, recs, config=DOSSIER_CONFIG, generator=gen) if gen
               else markovian.dossier(series_id, recs, config=DOSSIER_CONFIG))
        self.deps.tracer.emit(AGENT, "dossier", input_summary=f"{series_id} {len(recs)} records",
                              output_summary=f"{out['chunks']} chunks, cited {len(out['cited_ids'])}, "
                                             f"tokens {out['tokens_projected']}→{out['tokens_actual']}",
                              engine="markovian", status="ok")
        # model = None when every chunk fell back to the extractive generator (no model wrote any of it).
        model = self.receipts[-1][0] if self.receipts else None
        return {**out, "series_id": series_id, "record_count": len(recs), "model": model,
                "receipt_id": self.receipts[-1][1] if self.receipts else None,
                "receipt_ids": [r for _, r in self.receipts]}
