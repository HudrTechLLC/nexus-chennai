"""HTTP client for the engines sidecar (engines-ts/sidecar). Used when ENGINES_BACKEND=sidecar."""

from __future__ import annotations

from typing import Any

import httpx

from app.engines._runtime import sidecar_url


class SidecarError(RuntimeError):
    pass


# One pooled client. trust_env=False: the sidecar is local, and proxy discovery costs ~0.4 s per
# request on Windows.
_client = httpx.Client(trust_env=False)


def call(path: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    url = f"{sidecar_url()}/{path.lstrip('/')}"
    try:
        resp = _client.post(url, json=payload, timeout=timeout)
    except httpx.HTTPError as exc:
        raise SidecarError(f"engines sidecar unreachable at {url}: {exc}") from exc
    if resp.status_code != 200:
        raise SidecarError(f"engines sidecar {path} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()
