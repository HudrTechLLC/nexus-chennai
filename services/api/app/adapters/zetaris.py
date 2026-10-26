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
from typing import Any, Callable

import duckdb
import httpx

from ..config import Settings, load_city
from ..tracing import Tracer
from .zetaris_sources import localise


class ZetarisError(RuntimeError):
    pass


class UnknownQuery(ZetarisError):
    pass


class ZetarisTimeout(ZetarisError):
    """The query timed out, or was skipped because it timed out earlier in this run (fail-fast breaker)."""


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
    # Values for optional parameters; the caller's params override them.
    defaults: dict[str, Any] | None = None
    # Live-only hooks (q_dq_flags, 0007_14; agreed with nexus-1). None of them touches the sample path, so sample
    # mode stays byte-identical.
    # expand: params -> one or more param dicts for the Lightning SQL (e.g. a comma-joined id list into fixed
    # :id01.. slots so `IN (...)` pushes down to Postgres); several dicts run as several calls whose rows are merged.
    expand: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None
    # lightning_files: the Lightning SQL to use instead when ZETARIS_DATA=files (still localised).
    lightning_files: str | None = None
    # as_of_column: `lightning` returns one extra last column (a freshness time) that is not part of `columns`;
    # it is stripped from the rows and its latest value goes into the trace as as_of=... A row whose first column is
    # NULL is a freshness marker only (so an empty answer still has a time) and is dropped.
    as_of_column: bool = False


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


def load_sample_views(con: duckdb.DuckDBPyConnection, sample_dir) -> None:
    """Create the bundle's views (data/sample/views.sql, e.g. v_crime_unified) on a sample connection.
    Missing file = no views (an older bundle). The file runs as one script (DuckDB executes every
    statement), so a ';' inside a string literal is safe."""
    from pathlib import Path

    path = Path(sample_dir) / "views.sql"
    if path.is_file():
        con.execute(path.read_text(encoding="utf-8"))


class ZetarisTransient(ZetarisError):
    """A Zetaris HTTP 400 that is really a connection failure between Zetaris and its JDBC source."""


# Zetaris reports Spark/JDBC failures as HTTP 400. These texts mean the source connection failed
# (seen live: intermittent DNS for the Supabase pooler inside the container), not bad SQL.
REST_ATTEMPTS = 3  # first try + at most 2 retries
TRANSIENT_400 = ("UnknownHostException", "The connection attempt failed")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TransportError, ZetarisTransient)):
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
        self._retries: dict[str, int] = {}  # query id -> retries taken (traced as retry_count)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.zetaris_api_key}",
            "X-Org-ID": self.settings.zetaris_org_id,
            "X-Request-ID": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

    def _run_rest(self, sql: str, query_id: str, limit: int) -> tuple[list[list[Any]], str]:
        """Run with at most REST_ATTEMPTS - 1 retries on transient failures. Zetaris refuses a reused queryId
        ("Query id already exists"), so every retry sends a fresh id; returns the rows and the id that answered,
        which is the one the trace and the alert card cite."""
        used = query_id
        for attempt in range(1, REST_ATTEMPTS + 1):
            try:
                return self._post(sql, used, limit), used
            except Exception as exc:
                if attempt == REST_ATTEMPTS or not _is_retryable(exc):
                    raise
                self._retries[query_id] = attempt
                time.sleep(min(0.5 * 2 ** (attempt - 1), 4.0))
                used = str(uuid.uuid4())
        raise AssertionError("unreachable")

    def _post(self, sql: str, query_id: str, limit: int, timeout: float | None = None) -> list[list[Any]]:
        body = {"queryId": query_id, "sql": sql, "source": "SqlEditor", "limit": limit}
        kw: dict[str, Any] = {} if timeout is None else {"timeout": httpx.Timeout(timeout)}
        resp = self._client.post("/sql-editor/sqls/run", json=body, headers=self._headers(), **kw)
        if resp.status_code == 401:
            raise ZetarisError("Zetaris rejected the API key (HTTP 401)")
        if resp.status_code == 400 and any(t in resp.text for t in TRANSIENT_400):
            raise ZetarisTransient(f"Zetaris source connection failed (transient): {resp.text[:300]}")
        if resp.status_code == 400:
            raise ZetarisError(f"Zetaris bad request (check X-Org-ID / SQL): {resp.text[:300]}")
        resp.raise_for_status()
        out = resp.json()
        return (out.get("data") if isinstance(out, dict) else None) or []

    def _run_sample(self, sql: str) -> list[list[Any]]:
        if self._duck is None:
            self._duck = duckdb.connect(":memory:")
            # The city's zone, never the host's: the twins' date logic (days, windows) must give the same rows on
            # an IST laptop and in a UTC container, or the judge examples do not reproduce (WS5-12).
            self._duck.execute(f"SET TimeZone = '{load_city(self.settings.city)['timezone']}'")
            self._duck.execute(f"SET file_search_path = '{self.settings.sample_dir.as_posix()}'")
            load_sample_views(self._duck, self.settings.sample_dir)
        return [list(r) for r in self._duck.execute(sql).fetchall()]

    def named(self, name: str, *, agent: str, limit: int = 1000, timeout_s: float | None = None,
              **params: Any) -> QueryResult:
        """Run one registered query. Agents call this, never raw SQL.

        `timeout_s` makes this call fail fast (one attempt, then the breaker) with at most that timeout, even for
        a query not declared fail-fast; the shorter of it and the query's own `timeout_s` applies."""
        q = self.registry.get(name)
        if q is None:
            raise UnknownQuery(f"'{name}' is not a registered named query")
        params = {**(q.defaults or {}), **params}
        caps = [t for t in (q.timeout_s, timeout_s) if t is not None]
        fast = min(caps) if caps else None
        query_id = str(uuid.uuid4())
        earlier: list[str] = []  # query ids of earlier batches (expand), cited in the trace with the last one
        started = time.perf_counter()
        source = "zetaris"
        if fast is not None and self._tripped.get(name, 0.0) > time.monotonic():
            msg = f"'{name}' skipped: it timed out within the last {int(BREAKER_SECONDS)} s"
            self._trace(agent, name, query_id, None, 0, "error", msg)
            raise ZetarisTimeout(msg)
        try:
            if self.settings.sample_mode and not self.settings.zetaris_api_key:
                raise httpx.ConnectError("sample mode without Zetaris credentials")
            files_sql = bool(q.lightning_files) and self.settings.zetaris_data == "files"
            template = localise(q.lightning_files if files_sql else q.lightning, self.settings.zetaris_data)
            batches = q.expand(params) if q.expand else [params]
            rows = []
            for n, batch in enumerate(batches):
                if n:
                    earlier.append(query_id)
                    query_id = str(uuid.uuid4())
                sql = render(template, batch)
                if fast is not None:
                    rows += self._post(sql, query_id, limit, fast)
                else:
                    got, used = self._run_rest(sql, query_id, limit)
                    rows += got
                    if used != query_id:  # a retry answered: cite its id, keep the retry count
                        self._retries[used] = self._retries.pop(query_id, 0)
                        query_id = used
            if q.as_of_column and not files_sql:
                stamps = [str(r[-1]) for r in rows if r and r[-1] is not None]
                # A row whose first column is NULL is the query's freshness marker, not data: drop it.
                rows = [r[:-1] for r in rows if r and r[0] is not None]
                source = f"zetaris as_of={max(stamps)}" if stamps else "zetaris as_of=none"
            if len(batches) > 1:  # each batch is ordered; keep the merged answer in one order too (D-031)
                rows.sort(key=lambda r: tuple("" if v is None else str(v) for v in r))
                rows = rows[:limit] if limit else rows  # after the markers are gone, so no real row is lost
        except (httpx.TransportError, httpx.HTTPStatusError, ZetarisError) as exc:
            if fast is not None and isinstance(exc, httpx.TimeoutException):
                self._tripped[name] = time.monotonic() + BREAKER_SECONDS
            # Fall back only when Zetaris is unreachable or failing (transport / 5xx).
            # A 4xx (bad SQL, bad key) is a real error and must surface.
            if not (self.settings.sample_mode and _is_retryable(exc)):
                self._trace(agent, name, query_id, None, 0, "error", str(exc))
                if isinstance(exc, httpx.TimeoutException):
                    raise ZetarisTimeout(f"timed out: {exc}") from exc
                raise ZetarisError(str(exc)) from exc
            source = "sample"
            rows = self._run_sample(render(q.sample, params))[:limit]
        ms = int((time.perf_counter() - started) * 1000)
        bad = next((r for r in rows if q.columns and len(r) != len(q.columns)), None)
        if bad is not None:
            msg = f"'{name}' returned {len(bad)} columns via {source}, declared {len(q.columns)}"
            self._trace(agent, name, query_id, len(rows), ms, "error", msg)
            raise ZetarisError(msg)
        self._trace(agent, name, query_id, len(rows), ms, "ok", source, earlier)
        source = source.split(" ", 1)[0]  # the as_of note is for the trace; results say "zetaris" or "sample"
        if limit and len(rows) >= limit and self.tracer is not None:
            # D-031: Zetaris pushes the REST limit into the JDBC scan before filters it cannot push
            # down, so a full page may be a truncated scan rather than a complete answer. Never silent.
            self.tracer.emit(agent, "zetaris_result_truncated", input_summary=name,
                             output_summary=f"rows={len(rows)} limit={limit} via={source}",
                             zetaris_query_ids=[query_id], status="error")
        return QueryResult(name=name, query_id=query_id, rows=rows, ms=ms, source=source, columns=q.columns)

    def _trace(self, agent, name, query_id, rows, ms, status, note, earlier: list[str] | None = None) -> None:
        retries = self._retries.pop(query_id, 0)
        if self.tracer is None:
            return
        self.tracer.emit(
            agent,
            "zetaris_query",
            input_summary=name,
            output_summary=f"rows={rows} ms={ms} via={note}" + (f" retries={retries}" if retries else ""),
            zetaris_query_ids=[*(earlier or []), query_id],
            status=status,
            retry_count=retries,
        )

    def onboard(self, template: str, *args: Any, agent: str, limit: int = 1000, timeout_s: float = 120.0) -> QueryResult:
        """Run one source-onboarding statement (WS1-23). The caller names a template and gives its arguments; the
        SQL is built here from zetaris_onboard's fixed templates over generated onboard_* identifiers, never from
        text the caller passes. Live only: onboarding stages a real file in a real Zetaris."""
        from . import zetaris_onboard as zo

        builder = {"create_raw": zo.create_raw, "describe_raw": zo.describe_raw, "profile": zo.profile,
                   "examples": zo.examples, "dq": zo.dq, "dq_samples": zo.dq_samples,
                   "likely_duplicates": zo.likely_duplicates, "date_range": zo.date_range, "create_view": zo.create_view,
                   "count_view": zo.count_view}.get(template)
        if builder is None:
            raise ZetarisError(f"'{template}' is not an onboarding template")
        if not (self.settings.zetaris_api_key or "").strip():
            raise ZetarisError("source onboarding needs a live Zetaris (no API key set)")
        sql = builder(*args)
        name = f"onboard:{template}"
        query_id = str(uuid.uuid4())
        started = time.perf_counter()
        try:
            rows = self._post(sql, query_id, limit, timeout_s)
        except (httpx.TransportError, httpx.HTTPStatusError, ZetarisError) as exc:
            ms = int((time.perf_counter() - started) * 1000)
            self._trace(agent, name, query_id, None, ms, "error", f"{type(exc).__name__}: {str(exc)[:200]}")
            raise ZetarisError(f"{name} failed: {str(exc)[:300]}") from exc
        ms = int((time.perf_counter() - started) * 1000)
        self._trace(agent, name, query_id, len(rows), ms, "ok", "zetaris")
        return QueryResult(name=name, query_id=query_id, rows=rows, ms=ms, source="zetaris")

    def close(self) -> None:
        self._client.close()
        if self._duck is not None:
            self._duck.close()
