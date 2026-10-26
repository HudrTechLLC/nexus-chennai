"""Markovian facade (spec P6/E4): read a whole crime series in bounded chunks.

    from app.engines import markovian
    d = markovian.dossier("SER-7", records)
    # {"text", "cited_ids", "chunks", "tokens_projected", "tokens_actual", ...}

Each record is a dict with an `id` plus any of `kind`, `date`/`occurred_at`, `title`,
`text`/`summary`/`narrative`, `mo`/`mo_tags`, `status`. Records are packed in order into
chunks of at most `config.input_budget` estimated tokens; at most `max_chunks` chunks run.
The only state passed between chunks is the carryover block, capped at `carryover_tokens`.

The default generator is deterministic and extractive (sample mode: real logic, no canned
text). Pass `generator=` (prompt, batch, carryover, step) -> text to use a model; the
generator must end non-final chunks with `[STATE_CHECKPOINT]` + a state block.
Citations are filtered in code: a `[id]` that is not an input record id is removed from the
text and counted in `dropped_citations`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from app.engines import _runtime
from app.engines.markovian.core import (
    ChunkConfig,
    estimate_tokens,
    next_carryover,
    parse_markers,
    resolve_config,
    run_efficiency,
)

__all__ = ["dossier", "plan_chunks", "record_line", "DEFAULT_CONFIG", "ChunkConfig", "resolve_config"]

ENGINE = "markovian"
DEFAULT_CONFIG = resolve_config(chunk_size=4000, max_chunks=24, carryover_tokens=400)
Generator = Callable[[str, list[dict], str, int], str]

_TEXT_KEYS = ("text", "summary", "narrative", "description", "statement", "content", "title")
_DATE_KEYS = ("date", "occurred_at", "reported_at", "created_at", "at")
_STOP = set("""a an the and or of to in on at by for with from was were is are be been this that it its his her
their they he she them as after before near into over under one two three about also not no""".split())
_CITE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_./:-]*)\]")
_LEAD_KINDS = ("tip", "lead", "call", "anpr", "witness")


def _date(rec: dict[str, Any]) -> str:
    for k in _DATE_KEYS:
        if rec.get(k):
            return str(rec[k])[:10]
    return "undated"


def _body(rec: dict[str, Any]) -> str:
    for k in _TEXT_KEYS:
        if isinstance(rec.get(k), str) and rec[k].strip():
            return " ".join(rec[k].split())
    return ""


def record_line(rec: dict[str, Any]) -> str:
    """How a record enters a chunk: one line, id first so citations stay checkable."""
    mo = rec.get("mo_tags") or rec.get("mo") or []
    mo_s = f" MO: {', '.join(map(str, mo)) if isinstance(mo, list) else mo}." if mo else ""
    return f"[{rec['id']}] {_date(rec)} {rec.get('kind', 'record')}: {_body(rec)}{mo_s}".strip()


def plan_chunks(records: list[dict], cfg: ChunkConfig) -> list[list[tuple[dict, str]]]:
    """Greedy packing by estimated tokens. A record longer than the budget is truncated to fit."""
    budget = cfg.input_budget
    chunks: list[list[tuple[dict, str]]] = []
    current: list[tuple[dict, str]] = []
    used = 0
    for rec in records:
        line = record_line(rec)
        if estimate_tokens(line) > budget:
            line = line[: budget * 4 - 3] + "..."
        cost = estimate_tokens(line + "\n")
        if current and used + cost > budget:
            chunks.append(current)
            current, used = [], 0
        current.append((rec, line))
        used += cost
    if current:
        chunks.append(current)
    return chunks


# ------------------------------------------------------------ sample generator

def _parse_state(carryover: str) -> tuple[int, Counter, list[str]]:
    read = 0
    terms: Counter = Counter()
    leads: list[str] = []
    m = re.search(r"COMPLETED: read (\d+)", carryover)
    if m:
        read = int(m.group(1))
    m = re.search(r"DECISIONS: recurring MO ([^\n]*)", carryover)
    if m:
        for part in m.group(1).split(","):
            t = re.match(r"\s*([^\s]+) x(\d+)", part)
            if t:
                terms[t.group(1)] += int(t.group(2))
    m = re.search(r"CONTEXT: open leads ([^\n]*)", carryover)
    if m and m.group(1).strip() != "none":
        leads = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return read, terms, leads


def _terms(rec: dict[str, Any]) -> list[str]:
    mo = rec.get("mo_tags") or rec.get("mo") or []
    if isinstance(mo, str):
        mo = [mo]
    words = [w for w in re.findall(r"[a-z][a-z0-9-]{2,}", " ".join(map(str, mo)).lower()) if w not in _STOP]
    if not words:
        words = [w for w in re.findall(r"[a-z][a-z0-9-]{3,}", _body(rec).lower()) if w not in _STOP]
    return list(dict.fromkeys(words))


def make_sample_generator(total: int) -> Generator:
    """Extractive notes + a state block. State crosses chunks only through the carryover."""

    def generate(prompt: str, batch: list[dict], carryover: str, step: int) -> str:
        read, terms, leads = _parse_state(carryover)
        notes = []
        for rec in batch:
            body = _body(rec)
            first = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0][:160] if body else "(no text)"
            notes.append(f"- [{rec['id']}] {_date(rec)} {rec.get('kind', 'record')}: {first}")
            terms.update(_terms(rec))
            if str(rec.get("kind", "")).lower() in _LEAD_KINDS and str(rec.get("status", "open")).lower() != "closed":
                leads.append(rec["id"])
        read += len(batch)
        top = ", ".join(f"{t} x{n}" for t, n in terms.most_common(8)) or "none yet"
        lead_s = ", ".join(leads[-6:]) or "none"
        state = (f"COMPLETED: read {read} of {total} records\nREMAINING: {total - read} records\n"
                 f"DECISIONS: recurring MO {top}\nCONTEXT: open leads {lead_s}")
        marker = "[TASK_COMPLETE]" if read >= total else ""
        return "\n".join(notes) + f"\n{marker}\n[STATE_CHECKPOINT]\n{state}"

    return generate


def _compose(series_id: str, notes: list[str], carryover: str, total: int, read: int) -> str:
    _, terms, leads = _parse_state(carryover)
    dated = sorted(notes, key=lambda n: (re.search(r"\] (\S+)", n).group(1) if re.search(r"\] (\S+)", n) else ""))
    mo = ", ".join(f"{t} ({n} records)" for t, n in terms.most_common(5)) or "no recurring MO terms"
    steps = []
    if leads:
        steps.append(f"Follow up open leads {', '.join(f'[{x}]' for x in leads[-6:])}.")
    if terms:
        steps.append(f"Search other stations for '{terms.most_common(1)[0][0]}' in the same period.")
    if read < total:
        steps.append(f"{total - read} records were not read (chunk limit); rerun with a larger budget.")
    steps = steps or ["No open leads in the records read."]
    return "\n".join([
        f"# Series dossier {series_id}",
        f"Read {read} of {total} records.",
        "## Timeline", *dated,
        "## Consistent MO", mo,
        "## Open leads", ", ".join(f"[{x}]" for x in leads[-6:]) or "none",
        "## Recommended next steps", *[f"- {s}" for s in steps],
    ])


# --------------------------------------------------------------------- facade

def dossier(series_id: str, records: list[dict], *, config: ChunkConfig | None = None,
            generator: Generator | None = None) -> dict:
    cfg = config or DEFAULT_CONFIG
    ids = [str(r["id"]) for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("record ids must be unique")
    plan = plan_chunks(records, cfg)
    planned = len(plan)
    run_plan = plan[: cfg.max_chunks]
    gen = generator or make_sample_generator(len(records))

    if _runtime.backend() == "sidecar" and generator is None:
        from app.engines import _sidecar

        result = _sidecar.call("markovian/dossier", {
            "series_id": series_id, "config": cfg.as_dict(),
            "chunks": [[{"record": r, "line": line} for r, line in batch] for batch in run_plan],
            "total": len(records)})
        chunks_info, notes, carryover = result["chunks"], result["notes"], result["carryover"]
    else:
        carryover, notes, chunks_info = "", [], []
        for step, batch in enumerate(run_plan, start=1):
            batch_recs = [r for r, _ in batch]
            raw = gen("\n".join(line for _, line in batch), batch_recs, carryover, step)
            state, _done, cleaned = parse_markers(raw)
            input_tokens = sum(estimate_tokens(line + "\n") for _, line in batch)
            carryover, level = next_carryover(state, carryover, raw, cfg.carryover_tokens)
            notes += [ln for ln in cleaned.splitlines() if ln.strip()]
            chunks_info.append({"step": step, "record_ids": [str(r["id"]) for r in batch_recs],
                                "input_tokens": input_tokens, "output_tokens": estimate_tokens(cleaned),
                                "carryover_tokens": estimate_tokens(carryover), "carryover_level": level})

    read = sum(len(c["record_ids"]) for c in chunks_info)
    text = _compose(series_id, notes, carryover, len(records), read)
    known = set(ids)
    dropped = sorted({c for c in _CITE.findall(text) if c not in known})
    if dropped:
        text = _CITE.sub(lambda m: m.group(0) if m.group(1) in known else "", text)
    cited = list(dict.fromkeys(c for c in _CITE.findall(text) if c in known))

    eff = run_efficiency([c["input_tokens"] + c["output_tokens"] for c in chunks_info], cfg)
    out = {
        "text": text,
        "cited_ids": cited,
        "chunks": len(chunks_info),
        "tokens_projected": eff["standardCost"],
        "tokens_actual": eff["markovianCost"],
        "tokens_saved": eff["tokensSaved"],
        "token_label": "estimated",
        "chunks_planned": planned,
        "status": "completed" if planned <= cfg.max_chunks else "max-chunks",
        "unread_ids": [str(r["id"]) for batch in plan[cfg.max_chunks:] for r, _ in batch],
        "dropped_citations": dropped,
        "chunk_log": chunks_info,
        "config": cfg.as_dict(),
    }
    _log_run(series_id, out)
    _runtime.emit(ENGINE, "dossier", f"series {series_id}: {len(records)} records",
                  f"{out['chunks']} chunks, projected {out['tokens_projected']} vs actual {out['tokens_actual']} "
                  f"tokens (estimated), {len(cited)} cited ids")
    return out


def _log_run(series_id: str, out: dict) -> None:
    """Projected vs actual savings, one JSON line per run, next to the trace (logs/markovian_runs.jsonl)."""
    path = _runtime.get_tracer().path.parent / "markovian_runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "series_id": series_id,
            **{k: out[k] for k in ("chunks", "chunks_planned", "tokens_projected", "tokens_actual", "tokens_saved",
                                   "token_label", "status", "config")}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
