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

    def close(self) -> None:
        self._client.close()
