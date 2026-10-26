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
from collections.abc import Mapping, Sequence
from typing import Any

from .base import AgentDeps, AgentError, crime_from_row, features_from_row, short

AGENT = "Series analyst"
MIN_SERIES = 3

CHUNK_PROMPT = """You are building a crime-series dossier for police analysts, one chunk of records at a time.
Records (each starts with its [id]):
{records}

What you have learned so far (carryover state):
{carryover}

Write concise notes on this chunk: timeline points, consistent MO, open leads. Cite records as [id] using ONLY
the ids shown above. Never mention religion, caste or community. {final}
Then write the line [STATE_CHECKPOINT] followed by an updated state of at most 6 lines:
COMPLETED: read N of {total} records
REMAINING: ...
DECISIONS: recurring MO ...
CONTEXT: open leads ..."""


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


class SeriesAnalyst:
    def __init__(self, deps: AgentDeps) -> None:
        self.deps = deps

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
            tips, _ = self.deps.query("q_tip_corroboration", agent=AGENT, crime_id=cid)
            for t in tips:  # the view holds Tip-Guard-clean tips only (E5)
                if t.get("tip_id") and t.get("text"):
                    recs.append({"id": t["tip_id"], "kind": "tip", "date": t.get("received_week"),
                                 "text": t["text"]})
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
            try:
                self.deps.check_deadline(AGENT)
                res = self.deps.nightshift.chat("reason", [{"role": "user", "content": content}], agent=AGENT,
                                                purpose=f"dossier chunk {step}", max_tokens=2048, temperature=0.2)
                text = res.content or ""
                if "[STATE_CHECKPOINT]" not in text:
                    raise AgentError("no state checkpoint in chunk notes")
                return text
            except Exception as exc:
                self.deps.tracer.emit(AGENT, "chunk_fallback", input_summary=f"chunk {step}",
                                      output_summary=short(str(exc)), engine="markovian", status="degraded")
                return fallback(prompt, batch, carryover, step)

        return generate

    def dossier(self, series_id: str, crime_ids: Sequence[str], use_model: bool = True) -> dict[str, Any]:
        recs = self.records(crime_ids)
        if not recs:
            raise AgentError(f"series {series_id}: no records found")
        markovian = self.deps.engines.markovian
        gen = self._generator(len(recs)) if use_model else None
        out = markovian.dossier(series_id, recs, generator=gen) if gen else markovian.dossier(series_id, recs)
        self.deps.tracer.emit(AGENT, "dossier", input_summary=f"{series_id} {len(recs)} records",
                              output_summary=f"{out['chunks']} chunks, cited {len(out['cited_ids'])}, "
                                             f"tokens {out['tokens_projected']}→{out['tokens_actual']}",
                              engine="markovian", status="ok")
        return {**out, "series_id": series_id, "record_count": len(recs)}
