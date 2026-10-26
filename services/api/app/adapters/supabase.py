"""Supabase adapter: writes to the system of record (spec C1 rule 2).

Agents never read crime data from here; they read through Zetaris (rule R1). The
service-role key is used only by this API process, never by the web app or Vercel
(engg/docs/DECISIONS.md D-003).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings


class SupabaseError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._client = httpx.Client(base_url=settings.supabase_url.rstrip("/"), timeout=30, transport=transport)

    @property
    def configured(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_role_key)

    def _headers(self) -> dict[str, str]:
        key = self.settings.supabase_service_role_key
        return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def health(self) -> bool:
        """True if the Auth health endpoint answers with the configured key."""
        if not self.configured:
            return False
        resp = self._client.get("/auth/v1/health", headers=self._headers())
        return resp.status_code == 200

    def insert(self, table: str, rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        if not self.configured:
            raise SupabaseError("Supabase is not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")
        resp = self._client.post(
            f"/rest/v1/{table}",
            json=rows,
            headers={**self._headers(), "Prefer": "return=representation"},
        )
        if resp.status_code >= 400:
            raise SupabaseError(f"insert into {table} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    # ----- additive (WS2-16 worker + store; approved by nexus-chief) -------------
    # The worker reads queue/state tables only (alert_decisions, tips, runs, profiles,
    # link_alerts). Agent reasoning over crime data still goes through Zetaris (R1).

    def _require(self) -> None:
        if not self.configured:
            raise SupabaseError("Supabase is not configured (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)")

    def upsert(self, table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str) -> list[dict[str, Any]]:
        """Insert or update on the given unique columns (PostgREST merge-duplicates).

        Only the columns present in `rows` are written, so omitted columns keep their stored values.
        """
        self._require()
        resp = self._client.post(
            f"/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            json=rows,
            headers={**self._headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
        )
        if resp.status_code >= 400:
            raise SupabaseError(f"upsert into {table} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def select(self, table: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        """PostgREST select, e.g. params={"select": "*", "processed_at": "is.null", "limit": "50"}."""
        self._require()
        resp = self._client.get(f"/rest/v1/{table}", params=params or {"select": "*"}, headers=self._headers())
        if resp.status_code >= 400:
            raise SupabaseError(f"select from {table} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def update(self, table: str, match: dict[str, str], values: dict[str, Any]) -> list[dict[str, Any]]:
        """PATCH rows matching PostgREST filters, e.g. match={"alert_id": "eq.LA-1"}. A filter is required."""
        self._require()
        if not match:
            raise SupabaseError("update needs at least one filter; refusing to update every row")
        resp = self._client.patch(
            f"/rest/v1/{table}",
            params=match,
            json=values,
            headers={**self._headers(), "Prefer": "return=representation"},
        )
        if resp.status_code >= 400:
            raise SupabaseError(f"update of {table} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def rpc(self, fn: str, args: dict[str, Any]) -> Any:
        """Call a Postgres function through PostgREST (POST /rest/v1/rpc/<fn>) with the service role."""
        self._require()
        resp = self._client.post(f"/rest/v1/rpc/{fn}", json=args, headers=self._headers())
        if resp.status_code >= 400:
            raise SupabaseError(f"rpc {fn} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json() if resp.content else None

    def delete(self, table: str, match: dict[str, str]) -> list[dict[str, Any]]:
        """DELETE rows matching PostgREST filters. A filter is required (never deletes a whole table)."""
        self._require()
        if not match:
            raise SupabaseError("delete needs at least one filter; refusing to delete every row")
        resp = self._client.delete(f"/rest/v1/{table}", params=match,
                                   headers={**self._headers(), "Prefer": "return=representation"})
        if resp.status_code >= 400:
            raise SupabaseError(f"delete from {table} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def download(self, bucket: str, path: str) -> bytes:
        """Bytes of one Storage object (service role; private buckets). For evidence stills the Extractor reads."""
        self._require()
        resp = self._client.get(f"/storage/v1/object/{bucket}/{path.lstrip('/')}", headers=self._headers())
        if resp.status_code >= 400:
            raise SupabaseError(f"download {bucket}/{path} failed: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.content

    def close(self) -> None:
        self._client.close()
