"""Zetaris adapter: the only path for agent reads of crime data (rule R1).

REST contract, confirmed against zetaris/getting-started @ 6a2fbaa (scripts/zetaris_sql.py):
- POST {ZETARIS_REST_URL}/sql-editor/sqls/run
  body {"queryId": <uuid>, "sql": ..., "source": "SqlEditor", "limit": n}
- headers: Authorization Bearer <api key>, X-Org-ID, a fresh UUID X-Request-ID
- response {"data": [[...], ...]}
- one statement per call, no trailing semicolon

Agents may run only the named queries registered in NAMED_QUERIES (spec E5). Each
call records its query id, row count and duration in the trace and on the result,
so an alert card can cite the exact query behind each fact.

Sample mode runs the same named query's DuckDB form over data/sample when Zetaris
is unreachable (spec P2).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import duckdb
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import Settings
from ..tracing import Tracer


class ZetarisError(RuntimeError):
    pass


class UnknownQuery(ZetarisError):
    pass


@dataclass(frozen=True)
class NamedQuery:
    """A governed query. `lightning` runs on Zetaris; `sample` runs on DuckDB over data/sample."""

    name: str
    lightning: str
    sample: str
    description: str = ""
    # Output column names, in order (D3 names where they exist). Both forms must return
    # exactly these columns; a width mismatch raises instead of mislabelling values.
    columns: tuple[str, ...] = ()
    # Fail fast: one attempt with this timeout (seconds), no retries, and a short circuit breaker. For
    # queries that are optional and can hang, e.g. q_news, where Zetaris calls back into this API.
    timeout_s: float | None = None


# After a fail-fast query times out, skip it for this long (per client; a client lives for one run).
BREAKER_SECONDS = 60.0


@dataclass
class QueryResult:
    name: str
    query_id: str
    rows: list[list[Any]]
    ms: int
    source: str  # "zetaris" or "sample"
    columns: tuple[str, ...] = ()

    def dicts(self) -> list[dict[str, Any]]:
        """Rows as dicts keyed by column name. Raises if the query declares no columns."""
        if not self.columns:
            raise ZetarisError(f"named query '{self.name}' declares no columns")
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]


# The registry grows with P2 (spec E5 lists the 12 named queries).
NAMED_QUERIES: dict[str, NamedQuery] = {
    "q_ping": NamedQuery("q_ping", "SELECT 1", "SELECT 1", "Connectivity check", ("one",)),
}

# Engines-lane queries (q_hex_counts, q_dq_flags, q_news): owned by nexus-2, agreed with nexus-1.
from .zetaris_queries_n2 import N2_SPECS  # noqa: E402

NAMED_QUERIES.update({name: NamedQuery(**spec) for name, spec in N2_SPECS.items()})

# Data-lane queries (q_case, q_features, ...): owned by nexus-1.
from .zetaris_queries_n1 import specs as _n1_specs  # noqa: E402

NAMED_QUERIES.update({n: NamedQuery(**s) for n, s in _n1_specs().items()})

_PARAM = re.compile(r":([a-z_][a-z0-9_]*)")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def render(sql: str, params: dict[str, Any]) -> str:
    """Bind :params as SQL literals. Only str/int/float/bool/None are allowed."""

    def lit(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        raise TypeError(f"Unsupported parameter type: {type(v).__name__}")

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in params:
            raise KeyError(f"Missing query parameter :{key}")
        return lit(params[key])

    return _PARAM.sub(sub, sql)


class ZetarisClient:
    def __init__(
        self,
        settings: Settings,
        tracer: Tracer | None = None,
        transport: httpx.BaseTransport | None = None,
        registry: dict[str, NamedQuery] | None = None,
    ) -> None:
        self.settings = settings
        self.tracer = tracer
        self.registry = registry if registry is not None else NAMED_QUERIES
        self._client = httpx.Client(
            base_url=settings.zetaris_rest_url.rstrip("/"),
            timeout=settings.zetaris_timeout_seconds,
            transport=transport,
        )
        self._duck: duckdb.DuckDBPyConnection | None = None
        self._tripped: dict[str, float] = {}  # fail-fast query name -> monotonic time it may run again

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.zetaris_api_key}",
            "X-Org-ID": self.settings.zetaris_org_id,
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=4),
        reraise=True,
    )
    def _run_rest(self, sql: str, query_id: str, limit: int) -> list[list[Any]]:
        return self._post(sql, query_id, limit)

    def _post(self, sql: str, query_id: str, limit: int, timeout: float | None = None) -> list[list[Any]]:
        body = {"queryId": query_id, "sql": sql, "source": "SqlEditor", "limit": limit}
        kw: dict[str, Any] = {} if timeout is None else {"timeout": httpx.Timeout(timeout)}
        resp = self._client.post("/sql-editor/sqls/run", json=body, headers=self._headers(), **kw)
        if resp.status_code == 401:
            raise ZetarisError("Zetaris rejected the API key (HTTP 401)")
        if resp.status_code == 400:
            raise ZetarisError(f"Zetaris bad request (check X-Org-ID / SQL): {resp.text[:300]}")
        resp.raise_for_status()
        out = resp.json()
        return (out.get("data") if isinstance(out, dict) else None) or []

    def _run_sample(self, sql: str) -> list[list[Any]]:
        if self._duck is None:
            self._duck = duckdb.connect(":memory:")
            self._duck.execute(f"SET file_search_path = '{self.settings.sample_dir.as_posix()}'")
        return [list(r) for r in self._duck.execute(sql).fetchall()]

    def named(self, name: str, *, agent: str, limit: int = 1000, **params: Any) -> QueryResult:
        """Run one registered query. Agents call this, never raw SQL."""
        q = self.registry.get(name)
        if q is None:
            raise UnknownQuery(f"'{name}' is not a registered named query")
        query_id = str(uuid.uuid4())
        started = time.perf_counter()
        source = "zetaris"
        if q.timeout_s is not None and self._tripped.get(name, 0.0) > time.monotonic():
            msg = f"'{name}' skipped: it timed out within the last {int(BREAKER_SECONDS)} s"
            self._trace(agent, name, query_id, None, 0, "error", msg)
            raise ZetarisError(msg)
        try:
            if self.settings.sample_mode and not self.settings.zetaris_api_key:
                raise httpx.ConnectError("sample mode without Zetaris credentials")
            sql = render(q.lightning, params)
            rows = (self._post(sql, query_id, limit, q.timeout_s) if q.timeout_s is not None
                    else self._run_rest(sql, query_id, limit))
        except (httpx.TransportError, httpx.HTTPStatusError, ZetarisError) as exc:
            if q.timeout_s is not None and isinstance(exc, httpx.TimeoutException):
                self._tripped[name] = time.monotonic() + BREAKER_SECONDS
            # Fall back only when Zetaris is unreachable or failing (transport / 5xx).
            # A 4xx (bad SQL, bad key) is a real error and must surface.
            if not (self.settings.sample_mode and _is_retryable(exc)):
                self._trace(agent, name, query_id, None, 0, "error", str(exc))
                raise ZetarisError(str(exc)) from exc
            source = "sample"
            rows = self._run_sample(render(q.sample, params))[:limit]
        ms = int((time.perf_counter() - started) * 1000)
        bad = next((r for r in rows if q.columns and len(r) != len(q.columns)), None)
        if bad is not None:
            msg = f"'{name}' returned {len(bad)} columns via {source}, declared {len(q.columns)}"
            self._trace(agent, name, query_id, len(rows), ms, "error", msg)
            raise ZetarisError(msg)
        self._trace(agent, name, query_id, len(rows), ms, "ok", source)
        return QueryResult(name=name, query_id=query_id, rows=rows, ms=ms, source=source, columns=q.columns)

    def _trace(self, agent, name, query_id, rows, ms, status, note) -> None:
        if self.tracer is None:
            return
        self.tracer.emit(
            agent,
            "zetaris_query",
            input_summary=name,
            output_summary=f"rows={rows} ms={ms} via={note}",
            zetaris_query_ids=[query_id],
            status=status,
        )

    def close(self) -> None:
        self._client.close()
        if self._duck is not None:
            self._duck.close()
