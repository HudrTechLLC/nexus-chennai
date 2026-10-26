"""WS1-16: synthetic news/social REST feeds (API side), zetaris/40_feeds.sql shape, q_news DuckDB twin."""

import json
import re
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient
from app.config import Settings
from app.main import app
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]

NEWS = [
    {"article_id": "NEWS-1", "outlet": "Chennai Daily (synthetic)", "published_at": "2026-10-15T07:00:00+05:30",
     "headline": "Woman loses chain to bike-borne duo", "body": "...", "places_mentioned": ["L.B. Road"],
     "url": "https://example.invalid/news/1", "synthetic": True},
    {"article_id": "NEWS-2", "outlet": "Chennai Daily (synthetic)", "published_at": "2026-10-21T07:00:00+05:30",
     "headline": "Chain snatchers strike again", "body": "...", "places_mentioned": ["LB Road"],
     "url": "https://example.invalid/news/2", "synthetic": True},   # 6.5 days later: outside the window
    {"article_id": "NEWS-3", "outlet": "Chennai Daily (synthetic)", "published_at": "2026-10-15T09:00:00+05:30",
     "headline": "Theft at Anna Nagar market", "body": "...", "places_mentioned": ["Anna Nagar"],
     "url": "https://example.invalid/news/3", "synthetic": True},   # another station
    {"article_id": "NEWS-4", "outlet": "Real Paper", "published_at": "2026-10-15T08:00:00+05:30",
     "headline": "Not synthetic", "body": "...", "places_mentioned": ["Adyar"], "url": "https://x", "synthetic": False},
    {"article_id": "NEWS-5", "outlet": "Chennai Daily (synthetic)", "published_at": "2026-10-16T10:00:00+05:30",
     "headline": "Residents demand more patrols", "body": "...", "places_mentioned": ["Kotturpuram", "Adyar"],
     "url": "https://example.invalid/news/5", "synthetic": True},   # ward alias + station alias: one row
]
SOCIAL = [{"post_id": "SP-1", "platform": "x", "posted_at": "2026-10-14T20:00:00+05:30", "handle": "u***1",
           "text": "two guys on a red bike near LB road", "places_mentioned": ["LB Road"], "hashtags": ["chennai"],
           "synthetic": True}]
ALIASES = "alias,canonical,station_id,ward_no\nL.B. Road,Adyar,PS-ADYAR-J2,173\nLB Road,Adyar,PS-ADYAR-J2,173\n" \
          "Adyar,Adyar,PS-ADYAR-J2,173\nKotturpuram,Kotturpuram,PS-KOTTURPURAM-E5,170\n" \
          "Anna Nagar,Anna Nagar,PS-ANNANAGAR-K4,100\n"


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    d = tmp_path / "sample"
    for sub in ("sb", "news", "social", "ref"):
        (d / sub).mkdir(parents=True)
    (d / "news" / "articles.jsonl").write_text("\n".join(json.dumps(r) for r in NEWS) + "\n", encoding="utf-8")
    (d / "social" / "posts.jsonl").write_text("\n".join(json.dumps(r) for r in SOCIAL) + "\n", encoding="utf-8")
    (d / "ref" / "place_aliases.csv").write_text(ALIASES, encoding="utf-8")
    duckdb.connect().execute(
        "COPY (SELECT * FROM (VALUES ('CHN-AD-1', 'PS-ADYAR-J2', 170, 'chain_snatching', '2026-10-14T19:00:00+05:30'),"
        " ('CHN-AD-2', 'PS-ADYAR-J2', 173, 'theft', '2026-09-01T10:00:00+05:30'))"
        " t(crime_id, station_id, ward_no, category, occurred_from))"
        f" TO '{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    monkeypatch.setenv("FEEDS_DIR", str(d))
    return d


def test_news_feed_serves_only_synthetic_items_wrapped_in_an_object(bundle):
    body = TestClient(app).get("/mock-feeds/news").json()
    assert body["synthetic"] is True and body["count"] == 4
    assert [i["article_id"] for i in body["items"]] == ["NEWS-1", "NEWS-3", "NEWS-5", "NEWS-2"]
    assert all(i["synthetic"] is True for i in body["items"])


def test_since_until_filter_and_bad_dates(bundle):
    c = TestClient(app)
    got = c.get("/mock-feeds/news", params={"since": "2026-10-15T08:00:00+05:30", "until": "2026-10-20"}).json()
    assert [i["article_id"] for i in got["items"]] == ["NEWS-3", "NEWS-5"]
    assert c.get("/mock-feeds/news", params={"since": "yesterday"}).status_code == 422
    assert c.get("/mock-feeds/social").json()["items"][0]["post_id"] == "SP-1"


def test_missing_feed_file_is_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDS_DIR", str(tmp_path))
    assert TestClient(app).get("/mock-feeds/social").json() == {"items": [], "count": 0, "synthetic": True}


def test_q_news_twin_matches_by_alias_station_or_ward_within_the_window(bundle, tmp_path):
    client = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                           tracer=Tracer("t", tmp_path, echo=False))
    client._duck = duckdb.connect(":memory:")
    client._duck.execute(f"SET file_search_path = '{bundle.as_posix()}'")
    res = client.named("q_news", agent="Extractor", crime_id="CHN-AD-1")
    assert res.source == "sample" and res.columns == NAMED_QUERIES["q_news"].columns
    rows = res.dicts()
    assert [r["article_id"] for r in rows] == ["NEWS-1", "NEWS-5"]          # NEWS-2 too late, NEWS-3 elsewhere
    first = rows[0]
    assert first["matched_place"] == "Adyar" and first["hours_after"] == 12 and first["category_hint"] is True
    assert rows[1]["category_hint"] is False                                 # place match only
    assert client.named("q_news", agent="Extractor", crime_id="CHN-AD-2").rows == []


def test_feeds_sql_shape():
    sql = (ROOT / "zetaris" / "40_feeds.sql").read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    statements = [s.strip() for s in re.split(r";\s*(?:\n|$)", code) if s.strip()]
    assert len(statements) == 6
    assert statements[0].startswith("CREATE LIGHTNING DATABASE nexus_feeds")
    assert all("WITH CONTAINER nexus AS" in s for s in statements[3:])
    assert "{{since}}" in sql and "{{until}}" in sql and "mock-feeds/news" in sql and "mock-feeds/social" in sql
    assert "INTERVAL 4 DAYS" in sql and "s3csv.place_aliases" in sql
    assert not re.search(r"(sb_secret|Bearer |api[_-]?key)", sql, re.I)
