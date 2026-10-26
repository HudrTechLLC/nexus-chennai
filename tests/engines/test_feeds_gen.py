"""WS1-16: the seeded feed generator and the committed sample slice (data/sample/news, data/sample/social)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import feeds_gen
from app.adapters.zetaris import ZetarisClient
from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "sample"
NEWS_KEYS = {"article_id": str, "outlet": str, "published_at": str, "headline": str, "body": str,
             "places_mentioned": list, "url": str, "synthetic": bool}
POST_KEYS = {"post_id": str, "platform": str, "posted_at": str, "handle": str, "text": str,
             "places_mentioned": list, "hashtags": list, "synthetic": bool}


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_committed_slice_is_the_generator_output():
    articles, posts = feeds_gen.build_sample(SAMPLE)
    assert _jsonl(SAMPLE / "news" / "articles.jsonl") == articles, "regenerate: python -m app.feeds_gen --sample"
    assert _jsonl(SAMPLE / "social" / "posts.jsonl") == posts
    assert 20 <= len(articles) <= 200 and 20 <= len(posts) <= 300


@pytest.mark.parametrize("name,keys", [("news/articles.jsonl", NEWS_KEYS), ("social/posts.jsonl", POST_KEYS)])
def test_every_item_has_one_shape(name, keys):
    # Zetaris infers a REST table's schema from the response: same fields, same types, no empty lists.
    for row in _jsonl(SAMPLE / name):
        assert set(row) == set(keys)
        assert all(isinstance(row[k], t) for k, t in keys.items())
        assert row["synthetic"] is True and row["places_mentioned"]
        ts = row.get("published_at") or row["posted_at"]
        assert datetime.fromisoformat(ts).utcoffset() is not None  # explicit offset, read the same everywhere


def test_judge_cases_get_their_news_in_sample_mode():
    z = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""))
    hero = z.named("q_news", agent="t", crime_id="CHN-AD-2026-001182")
    assert hero.source == "sample"
    (row,) = hero.dicts()
    # Written with a local alias, resolved to the canonical place through ref/place_aliases.csv.
    assert row["matched_place"] == "Lattice Bridge Road" and 0 <= row["hours_after"] < 96
    (cab,) = z.named("q_news", agent="t", crime_id="CHN-GU-2025-000945").dicts()
    assert cab["category_hint"] is True and cab["matched_place"] == "Guindy"


def test_default_slice_never_ties_two_incidents_together():
    # Roundups are off (feeds_gen.ROUNDUPS): no committed article names two different stations' places.
    import csv

    with open(SAMPLE / "ref" / "place_aliases.csv", encoding="utf-8", newline="") as fh:
        station = {r["alias"]: r["station_id"] for r in csv.DictReader(fh)}
    for a in _jsonl(SAMPLE / "news" / "articles.jsonl"):
        assert len({station.get(p, p) for p in a["places_mentioned"]}) == 1


def test_roundups_name_both_places_inside_both_windows():
    tz = timezone(timedelta(hours=5, minutes=30))
    t0 = datetime(2026, 10, 14, 19, 40, tzinfo=tz)
    crimes = [{"crime_id": "A", "station_id": "S1", "sub_type": "chain_snatching", "occurred_from": t0},
              {"crime_id": "B", "station_id": "S2", "sub_type": "chain_snatching", "occurred_from": t0 + timedelta(days=2)}]
    aliases = [{"alias": "Alpha Rd", "canonical": "Alpha", "station_id": "S1"},
               {"alias": "Beta", "canonical": "Beta", "station_id": "S2"}]
    arts, _ = feeds_gen.generate(crimes, aliases, ["A", "B"], [["A", "B"]], roundups=True)
    (r,) = [a for a in arts if len(a["places_mentioned"]) == 2]
    at = datetime.fromisoformat(r["published_at"])
    assert r["places_mentioned"] == ["Alpha Rd", "Beta"] and t0 + timedelta(days=2) <= at < t0 + timedelta(days=4)
    assert feeds_gen.generate(crimes, aliases, ["A", "B"], [["A", "B"]], roundups=True) == (
        feeds_gen.generate(crimes, aliases, ["A", "B"], [["A", "B"]], roundups=True))  # deterministic


def test_mock_feeds_serves_the_slice_in_the_40_feeds_form(monkeypatch):
    # 40_feeds.sql calls ?since=YYYY-MM-DD&until=YYYY-MM-DD (naive dates); items carry offsets.
    from app.main import app

    monkeypatch.setenv("FEEDS_DIR", str(SAMPLE))
    c = TestClient(app)
    r = c.get("/mock-feeds/news", params={"since": "2026-10-01", "until": "2026-10-26"})
    assert r.status_code == 200 and r.json()["count"] >= 1
    r = c.get("/mock-feeds/social", params={"since": "2025-01-01", "until": "2026-12-31"})
    assert r.status_code == 200 and r.json()["count"] == len(_jsonl(SAMPLE / "social" / "posts.jsonl"))
