"""Shared plumbing for the agents (spec E3).

- `AgentDeps` carries the adapters, the tracer, the engines facade, the store and the
  run deadline. Every agent reads crime data only through `deps.zetaris.named(...)`
  (rule R1) and calls models only through `deps.nightshift.chat(lane, ...)` (rule R2).
- `rows_as_dicts` turns a Zetaris `QueryResult` into dicts with D3 column names.
- `parse_model_json` pulls the JSON object out of a model reply. Model output is only
  ever used for text (reasons, plans, MO labels); numbers are computed in code (R7).
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..adapters.nightshift import NightshiftError
from ..tracing import Tracer


class AgentError(RuntimeError):
    """An agent could not do its job (bad model output, missing data, deadline)."""


class DeadlineExceeded(AgentError):
    """The run passed its hard deadline (spec C4: 5 minutes)."""


class Store(Protocol):
    """Where agents write results (Supabase in live mode, memory in tests and sample runs)."""

    def upsert_features(self, features: dict[str, Any]) -> None: ...

    def write_alert(self, alert: dict[str, Any]) -> dict[str, Any]: ...

    def notify(self, notifications: list[dict[str, Any]]) -> None: ...

    def write_series(self, series: dict[str, Any], run_id: str) -> str: ...

    def write_dossier(self, series_id: str, dossier: dict[str, Any]) -> bool: ...


def series_name(series: Mapping[str, Any]) -> str:
    stations = list(series.get("stations") or [])
    where = ", ".join(stations[:3]) + (f" +{len(stations) - 3}" if len(stations) > 3 else "")
    return f"{len(series.get('crime_ids') or [])} linked cases" + (f" ({where})" if where else "")


def choose_series_id(series: Mapping[str, Any], existing: Mapping[str, str]) -> str:
    """Keep a series id stable as it grows: reuse the stored series sharing the most members.

    `existing` maps crime_id -> series_id for already-stored members. Ties go to the smaller id, so the
    choice is deterministic. A series with no stored members keeps its content-hash id.
    """
    overlap: dict[str, int] = {}
    for cid in series.get("crime_ids") or []:
        if cid in existing:
            overlap[existing[cid]] = overlap.get(existing[cid], 0) + 1
    if not overlap:
        return str(series["series_id"])
    return sorted(overlap, key=lambda sid: (-overlap[sid], sid))[0]


@dataclass
class MemoryStore:
    """In-memory store: used by tests and by sample-mode runs without Supabase."""

    features: dict[str, dict[str, Any]] = field(default_factory=dict)
    alerts: dict[str, dict[str, Any]] = field(default_factory=dict)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    series: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert_features(self, features: dict[str, Any]) -> None:
        self.features[features["crime_id"]] = features

    def write_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        self.alerts[alert["alert_id"]] = alert
        return alert

    def notify(self, notifications: list[dict[str, Any]]) -> None:
        self.notifications.extend(notifications)

    def write_series(self, series: dict[str, Any], run_id: str) -> str:
        existing = {cid: sid for sid, s in self.series.items() for cid in s["crime_ids"]}
        sid = choose_series_id(series, existing)
        row = self.series.setdefault(sid, {"series_id": sid, "crime_ids": [], "dossier": None, "status": "candidate"})
        row.update(name=series_name(series), run_id=run_id, synthetic=True,
                   crime_ids=sorted(set(row["crime_ids"]) | set(series.get("crime_ids") or [])))
        return sid

    def write_dossier(self, series_id: str, dossier: dict[str, Any]) -> bool:
        self.series.setdefault(series_id, {"series_id": series_id, "crime_ids": []})["dossier"] = dossier
        return True


@dataclass
class AgentDeps:
    tracer: Tracer
    zetaris: Any  # app.adapters.zetaris.ZetarisClient (or a test double with .named)
    nightshift: Any  # app.adapters.nightshift.NightshiftClient (or a test double with .chat)
    engines: Any = None  # the app.engines facade (world_model, hmem, markovian, scout_intent)
    store: Store = field(default_factory=MemoryStore)
    deadline: float | None = None  # time.monotonic() value; None = no deadline

    def check_deadline(self, where: str) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            self.tracer.emit(where, "deadline_exceeded", status="error", output_summary="run deadline passed")
            raise DeadlineExceeded(f"Run deadline passed in {where}")

    def query(self, name: str, *, agent: str, **params: Any) -> tuple[list[dict[str, Any]], str]:
        """Run a named query and return (rows as dicts, query id)."""
        self.check_deadline(agent)
        res = self.zetaris.named(name, agent=agent, **params)
        return rows_as_dicts(res), res.query_id


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def rows_as_dicts(res: Any) -> list[dict[str, Any]]:
    """Rows of a QueryResult as dicts keyed by D3 column names.

    Uses `res.dicts()` when the adapter provides it, else `res.columns`. Fails loudly
    when neither exists: guessing column positions would silently corrupt scoring.
    """
    if hasattr(res, "dicts"):
        return list(res.dicts())
    cols = getattr(res, "columns", None)
    if not cols:
        raise AgentError(f"Query '{getattr(res, 'name', '?')}' returned rows without column names")
    out = []
    for row in res.rows:
        if len(row) != len(cols):
            raise AgentError(f"Query '{res.name}' row width {len(row)} != {len(cols)} columns")
        out.append(dict(zip(cols, row)))
    return out


def _maybe_json(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


# Columns that hold JSON (jsonb comes back from Zetaris/DuckDB as text).
JSON_COLUMNS = ("sections", "property", "vehicles", "offenders_described", "victims", "statements", "evidence",
                "forensics", "features", "mo", "entities", "visual_tags", "location", "crime_ids")


def crime_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise a flattened `q_case` / candidate row into the nested D3.1 shape."""
    c = {k: _maybe_json(v) if k in JSON_COLUMNS else v for k, v in row.items()}
    if not isinstance(c.get("location"), dict):
        c["location"] = {
            "lat": c.get("lat"),
            "lon": c.get("lon"),
            "address": c.get("address"),
            "ward": c.get("ward", c.get("ward_no")),
            "h3_r9": c.get("h3_r9"),
            "geohash7": c.get("geohash7"),
        }
    for key in ("vehicles", "offenders_described", "statements", "evidence", "forensics"):
        if c.get(key) is None:
            c[key] = []
    return c


def features_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise a `q_features` row into the D3.2 shape (MO may come flattened as mo_* columns)."""
    f = {k: _maybe_json(v) if k in JSON_COLUMNS else v for k, v in row.items()}
    if not isinstance(f.get("mo"), dict):
        f["mo"] = {k[3:]: _maybe_json(v) for k, v in row.items() if k.startswith("mo_")}
    if isinstance(f.get("visual_tags"), str):
        f["visual_tags"] = [t.strip() for t in f["visual_tags"].split(",") if t.strip()]
    return f


# ---------------------------------------------------------------------------
# Model output
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _json_objects(text: str) -> list[dict[str, Any]]:
    """All top-level JSON objects in `text`, in order."""
    found: list[dict[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        start = text.find("{", i)
        if start == -1:
            break
        depth = 0
        in_str = esc = False
        end = -1
        for j in range(start, n):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            i = start + 1
            continue
        try:
            obj = json.loads(text[start : end + 1])
        except ValueError:
            i = start + 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = end + 1
    return found


def parse_model_json(text: str) -> dict[str, Any]:
    """Return the LAST JSON object in a model reply.

    The Nemotron lanes are reasoning models and may put their thinking (including
    draft JSON) in the content before the answer (DECISIONS D-017), so the final
    object wins. Handles ``` fences and <think> blocks.
    """
    if not text:
        raise AgentError("Empty model reply")
    body = _THINK.sub("", text)
    fenced = [m.group(1) for m in _FENCE.finditer(body)]
    for cand in (fenced[::-1] if fenced else []) + [body]:
        objs = _json_objects(cand)
        if objs:
            return objs[-1]
    raise AgentError("No JSON object in model reply")


# Reasoning lanes spend hundreds of tokens thinking; small budgets return empty replies (D-017).
DEFAULT_MAX_TOKENS = 2048


def chat_json(
    deps: AgentDeps,
    lane: str,
    messages: list[dict[str, Any]],
    *,
    agent: str,
    purpose: str,
    retries: int = 1,
    thinking: bool = True,
    **params: Any,
) -> tuple[dict[str, Any], Any]:
    """Call a pinned lane and parse a JSON object; one corrective retry on bad or cut-off output.

    Nightshift failures (down, 4xx, no replay fixture) surface as AgentError so every
    agent's documented fallback runs instead of crashing the run.
    """
    deps.check_deadline(agent)
    params.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
    if not thinking:
        # Nemotron reasoning off (chat template switch, passed through by Nightshift). Measured live on
        # Lightning for one MO extraction: 4,088 completion tokens / 56 s with thinking, 110 / 12 s without;
        # with thinking on and max_tokens=2048 the provider returns an empty response (502).
        params.setdefault("chat_template_kwargs", {"enable_thinking": False})
    msgs = list(messages)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            result = deps.nightshift.chat(lane, msgs, agent=agent, purpose=purpose, **params)
        except NightshiftError as exc:
            raise AgentError(f"{agent}: model call failed for {purpose}: {exc}") from exc
        try:
            finish = ((getattr(result, "raw", None) or {}).get("choices") or [{}])[0].get("finish_reason")
            if finish == "length":
                # Cut off. Live Lightning sometimes repeats its answer until the budget runs out
                # (D-017): a complete object before the cut is the answer. If there is none,
                # retry with more room.
                objs = _json_objects(_THINK.sub("", result.content or ""))
                if objs:
                    deps.tracer.emit(agent, "model_output_truncated", input_summary=purpose, status="degraded",
                                     model=getattr(result, "model", None),
                                     output_summary=f"finish_reason=length; used last of {len(objs)} complete objects")
                    return objs[-1], result
                params["max_tokens"] = int(params["max_tokens"]) * 2
                raise AgentError("reply cut off at max_tokens (finish_reason=length)")
            return parse_model_json(result.content), result
        except AgentError as exc:
            last_err = exc
            deps.tracer.emit(agent, "model_output_invalid", input_summary=purpose, output_summary=str(exc),
                             model=getattr(result, "model", None), retry_count=attempt, status="retry")
            msgs = msgs + [
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": "Reply with one JSON object only, matching the schema. No prose."},
            ]
    raise AgentError(f"{agent}: model did not return valid JSON for {purpose}: {last_err}")


def short(v: Any, n: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"
