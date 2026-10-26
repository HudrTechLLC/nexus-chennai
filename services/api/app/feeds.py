"""Synthetic news and social REST feeds (spec D1 #16-17, Part H `GET /mock-feeds/*`; WS1-16). Owner: nexus-2.

Zetaris registers these endpoints as REST tables (zetaris/40_feeds.sql: rest_news, rest_social), so news
and social posts enter Nexus through Zetaris like every other source (rule R1).

    GET /mock-feeds/news?since=2026-10-01&until=2026-10-26    -> {"items": [...], "count": n, "synthetic": true}
    GET /mock-feeds/social?since=...&until=...

Items are read from the sample bundle (`data/sample/news/articles.jsonl`, `data/sample/social/posts.jsonl`;
FEEDS_DIR overrides the base folder, e.g. data/generated for the full set). Only rows marked `synthetic: true` are served (rule R9). The response wraps items in an
object because Zetaris REST tables infer their schema from a JSON object (getting-started companion §2).
No database reads, no auth: this is public mock data.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/mock-feeds", tags=["mock-feeds"])

FEEDS = {
    "news": {"file": "news/articles.jsonl", "time": "published_at", "id": "article_id"},
    "social": {"file": "social/posts.jsonl", "time": "posted_at", "id": "post_id"},
}
MAX_ITEMS = 5000


def feeds_dir() -> Path:
    env = os.environ.get("FEEDS_DIR")
    if env:
        return Path(env)
    from .config import get_settings

    return get_settings().sample_dir


@lru_cache(maxsize=8)
def _load(path: str, mtime: float) -> tuple[dict, ...]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                if row.get("synthetic") is True:
                    rows.append(row)
    return tuple(rows)


def _parse(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be an ISO date or datetime") from exc


def _cmp(ts: str, bound: datetime) -> tuple[datetime, datetime]:
    t = datetime.fromisoformat(ts)
    if (t.tzinfo is None) != (bound.tzinfo is None):  # compare naive with naive
        t, bound = t.replace(tzinfo=None), bound.replace(tzinfo=None)
    return t, bound


def items(feed: str, since: str | None = None, until: str | None = None, limit: int = MAX_ITEMS) -> list[dict]:
    spec = FEEDS[feed]
    path = feeds_dir() / spec["file"]
    if not path.exists():
        return []
    s, u = _parse(since, "since"), _parse(until, "until")
    out = []
    for row in _load(str(path), path.stat().st_mtime):
        ts = row.get(spec["time"])
        if not ts:
            continue
        if s is not None:
            t, b = _cmp(ts, s)
            if t < b:
                continue
        if u is not None:
            t, b = _cmp(ts, u)
            if t >= b:
                continue
        out.append(row)
    out.sort(key=lambda r: (r[spec["time"]], r.get(spec["id"], "")))
    return out[:limit]


def _response(feed: str, since: str | None, until: str | None, limit: int) -> dict:
    rows = items(feed, since, until, limit)
    return {"items": rows, "count": len(rows), "synthetic": True}


@router.get("/news")
def news(since: str | None = Query(None), until: str | None = Query(None),
         limit: int = Query(MAX_ITEMS, ge=1, le=MAX_ITEMS)) -> dict:
    return _response("news", since, until, limit)


@router.get("/social")
def social(since: str | None = Query(None), until: str | None = Query(None),
           limit: int = Query(MAX_ITEMS, ge=1, le=MAX_ITEMS)) -> dict:
    return _response("social", since, until, limit)
