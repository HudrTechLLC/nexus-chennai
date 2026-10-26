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
import json
import re
from collections.abc import Mapping, Sequence, Set
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


# ----- dossier display merge (code, no model) ------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_DATED = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\b")
_YEAR = re.compile(r"\b(20\d\d)\b")
_TRAILING_CITES = re.compile(r"((?:\s*\[[A-Za-z0-9][A-Za-z0-9_./:-]*\])+)\s*$")
_MO_LINE = re.compile(r"^(consistent\s+mo|recurring\s+mo|mo)\b", re.IGNORECASE)
_PSEUDO_HEADING = re.compile(r"^\*\*[^*]+\*\*:?$")


def _date_key(body: str) -> tuple[int, int, int] | None:
    m = _DATED.match(body)
    if not m or m.group(2).lower() not in _MONTHS:
        return None
    year = _YEAR.search(body.split(":", 1)[0]) or _YEAR.search(body)
    return (int(year.group(1)) if year else 0, _MONTHS[m.group(2).lower()], int(m.group(1)))


def merge_dossier_text(text: str) -> str:
    """One readable dossier from the Markovian chunks' concatenated notes, in code (no model).

    Live (SER-B687C36CFC): each chunk's "Timeline & MO Notes" / "Open Leads" headings repeated, some empty, and dated
    lines were out of order. The bullets under "## Timeline" are regrouped: dated lines into a date-sorted Timeline,
    MO statements into "Consistent MO", everything else into "Open leads". A bullet repeated across chunks is kept once
    with the union of its [id] citations, so every citation survives. Empty sections are dropped. Idempotent.
    """
    lines = text.splitlines()
    if "## Timeline" not in lines:
        return text
    start = lines.index("## Timeline")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    buckets: dict[str, dict[str, tuple[str, list[str]]]] = {"timeline": {}, "mo": {}, "leads": {}}

    def add(bucket: str, body: str) -> None:
        m = _TRAILING_CITES.search(body)
        cites = _CITED.findall(m.group(1)) if m else []
        core = body[: m.start()].rstrip() if m else body.strip()
        key = re.sub(r"\s+", " ", core).strip().lower()
        if key in buckets[bucket]:
            have = buckets[bucket][key][1]
            have.extend(c for c in cites if c not in have)
        else:
            buckets[bucket][key] = (core, list(dict.fromkeys(cites)))

    for raw in lines[start + 1:end]:
        s = raw.strip()
        if not s or _PSEUDO_HEADING.match(s):
            continue
        body = s[2:].strip() if s[:2] in ("- ", "* ") else s
        add("timeline" if _date_key(body) else "mo" if _MO_LINE.match(body) else "leads", body)

    def render(bucket: str) -> list[str]:
        items = list(buckets[bucket].values())
        if bucket == "timeline":
            items.sort(key=lambda it: _date_key(it[0]) or (0, 0, 0))
        return [f"- {core}" + "".join(f" [{c}]" for c in cites) for core, cites in items]

    tail: list[tuple[str, list[str]]] = []
    for line in lines[end:]:
        if line.startswith("## "):
            tail.append((line, []))
        elif tail and line.strip():
            tail[-1][1].append(line)
    # The chunks' own MO statements and leads replace the engine's summary lines for those sections (its MO line is
    # a tag count, "no recurring MO terms"; its leads are uncited carry-over phrases). Engine lines that cite a
    # record are kept, so no citation is lost.
    filled = {"## Consistent MO": render("mo"), "## Open leads": render("leads")}
    out_tail: list[tuple[str, list[str]]] = []
    for head, body in tail:
        mine = filled.pop(head, None)
        if mine:
            body = mine + [b for b in body if _CITED.search(b)]
        out_tail.append((head, body))
    if filled.get("## Consistent MO"):  # sections the engine did not write at all
        out_tail.insert(0, ("## Consistent MO", filled["## Consistent MO"]))
    if filled.get("## Open leads"):
        out_tail.append(("## Open leads", filled["## Open leads"]))

    out = lines[:start]
    if buckets["timeline"]:
        out += ["## Timeline", *render("timeline")]
    for head, body in out_tail:
        if body:
            out += [head, *body]
    return "\n".join(out)


def series_id_for(crime_ids: Sequence[str]) -> str:
    return "SER-" + hashlib.sha1("|".join(sorted(crime_ids)).encode("utf-8")).hexdigest()[:10].upper()


# D-033: a crime whose narrative starts with a bracketed label containing the word "test" (e.g.
# "[nexus-5 timing test FIR] ...") is a test filing. It keeps its pair alerts, but is never a series member.
TEST_FIR = re.compile(r"^\s*\[[^\]]*\btest\b[^\]]*\]", re.IGNORECASE)
TEST_FIR_REASON = "test FIR"


def is_test_fir(narrative: Any) -> bool:
    return isinstance(narrative, str) and bool(TEST_FIR.match(narrative))


def read_member_cases(deps: AgentDeps, crime_ids: Sequence[str]) -> dict[str, dict[str, Any]] | None:
    """{crime_id: q_cases row} for `crime_ids`, read through Zetaris (q_cases, R1); None when the read fails.

    A failed read is traced `test_fir_check_failed` (degraded): nothing is excluded or removed that run, and
    the next run that can read the cases applies D-033.
    """
    from ..adapters.zetaris_queries_n2 import cases_params
    ids = sorted({str(c) for c in crime_ids if c})
    rows_by_id: dict[str, dict[str, Any]] = {}
    if not ids:
        return rows_by_id
    try:
        for params in cases_params(ids):
            rows, _ = deps.query("q_cases", agent=AGENT, **params)
            for r in rows:
                if r.get("crime_id") in ids:
                    rows_by_id.setdefault(str(r["crime_id"]), r)
    except DeadlineExceeded:
        raise
    except Exception as exc:
        deps.tracer.emit(AGENT, "test_fir_check_failed", input_summary=f"{len(ids)} crimes",
                         output_summary=short(str(exc)), status="degraded")
        return None
    return rows_by_id


def flag_test_firs(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """{crime_id: reason} for the D-033 test FIRs among q_cases rows."""
    return {cid: TEST_FIR_REASON for cid, r in rows.items() if is_test_fir(r.get("narrative"))}


def find_test_firs(deps: AgentDeps, crime_ids: Sequence[str]) -> dict[str, str]:
    """{crime_id: reason} for the D-033 test FIRs among `crime_ids` ({} when the cases cannot be read)."""
    return flag_test_firs(read_member_cases(deps, crime_ids) or {})


# ----- series names (code-generated from the members' dominant MO; no model) --------------------------------

# Offender vehicle types, as the crime_vehicles table records them, to the word an analyst uses.
VEHICLE_WORDS = {
    "motorcycle": "two-wheeler", "motorbike": "two-wheeler", "bike": "two-wheeler", "scooter": "two-wheeler",
    "moped": "two-wheeler", "two_wheeler": "two-wheeler", "autorickshaw": "auto-rickshaw",
    "auto_rickshaw": "auto-rickshaw", "auto": "auto-rickshaw", "car": "car", "cab": "cab", "taxi": "cab",
}


def _majority(values: Sequence[Any], n: int) -> Any:
    """The value more than half of the n members share (ties impossible), or None."""
    counts: dict[Any, int] = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    best = sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return best[0][0] if best and best[0][1] * 2 > n else None


def _plural(label: str) -> str:
    words = label.replace("_", " ").replace("-", " ").split()
    if not words:
        return ""
    last = words[-1]
    if last.endswith("y") and last[-2:-1] not in ("a", "e", "i", "o", "u"):
        last = last[:-1] + "ies"
    elif last.endswith(("s", "sh", "ch", "x")):
        last += "es"
    else:
        last += "s"
    return " ".join(words[:-1] + [last])


def _json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def _offender_vehicle(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(vehicle word, colour) of the crime's first offender vehicle, or (None, None)."""
    for v in _json(row.get("vehicles")) or []:
        if isinstance(v, Mapping) and v.get("role") in (None, "", "used_by_offender"):
            kind = str(v.get("type") or v.get("vehicle_type") or "").strip().lower()
            word = VEHICLE_WORDS.get(kind) or (kind.replace("_", " ") or None)
            colour = str(v.get("colour") or "").strip().lower() or None
            return word, colour
    return None, None


def describe_series(rows: Sequence[Mapping[str, Any]]) -> str | None:
    """A name from the members' dominant MO, e.g. "Red two-wheeler chain snatchings · 3 stations".

    Deterministic and code-only. Each part appears only when more than half the members share it: the crime
    (sub-type, else category), the offender vehicle and its colour, else the approach. None when the members
    share no crime type (the caller keeps the plain "N linked cases" name).
    """
    n = len(rows)
    if not n:
        return None
    crime = _majority([r.get("sub_type") for r in rows], n) or _majority([r.get("category") for r in rows], n)
    if not crime:
        return None
    vehicles = [_offender_vehicle(r) for r in rows]
    vehicle = _majority([w for w, _ in vehicles], n)
    colour = _majority([c for w, c in vehicles if w == vehicle], n) if vehicle else None
    words = [w for w in (colour, vehicle, _plural(str(crime))) if w]
    if not vehicle:
        mos = [((_json(r.get("features")) or {}).get("mo") or {}) for r in rows]
        approach = _majority([m.get("approach") if isinstance(m, Mapping) else None for m in mos], n)
        if approach and approach not in ("unknown", "none"):
            words.append(f"({str(approach).replace('_', ' ')})")
    stations = len({r.get("station_id") for r in rows if r.get("station_id")})
    name = " ".join(words)
    name = name[:1].upper() + name[1:]
    # No case count: the console adds the member count next to the name (apps/web lib/overview seriesCount).
    return name + (f" · {stations} station{'s' if stations != 1 else ''}" if stations else "")


def detect_series(alerts: Sequence[Mapping[str, Any]], excluded: Set[str] = frozenset()) -> list[dict[str, Any]]:
    """Connected components of 3+ cases over pair alerts that are not rejected.

    `excluded` crimes (D-033 test FIRs) are left out before grouping, so they neither join a series nor bridge
    two series together.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = [a for a in alerts if a.get("kind", "pair") == "pair" and a.get("status") != "rejected"
             and len(a.get("crimes") or []) == 2 and not set(a["crimes"]) & excluded]
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
        return {**out, "text": merge_dossier_text(out.get("text") or ""),
                "series_id": series_id, "record_count": len(recs), "model": model,
                "receipt_id": self.receipts[-1][1] if self.receipts else None,
                "receipt_ids": [r for _, r in self.receipts]}
