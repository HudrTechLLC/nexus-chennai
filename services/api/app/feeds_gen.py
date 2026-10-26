"""Synthetic news and social feed generator (spec D1 #16-17, WS1-16). Owner: nexus-2.

Seeded and deterministic: the same crimes, aliases and seed give the same bytes. Every item is
`synthetic: true` (rule R9) and has every field with a fixed type, because Zetaris infers a REST table's
schema from the response (zetaris/40_feeds.sql).

What it writes, for a given set of "grounded" crimes:
- one local news report per grounded crime (most of them), published 2-90 h after it and naming a place
  alias of the crime's station, as written locally ("LB Road", "Adayar"), so q_news must resolve aliases;
- (ROUNDUPS, off by default) a roundup when two crimes of one series fall within ROUNDUP_DAYS ("second snatching this week"), naming
  both places and published inside the q_news window of both. This is the only kind of item that ties
  two incidents together (Linker corroboration);
- noise: civic stories that name a known place but no crime (category_hint false), stories about places
  outside the alias list, and stories outside every window;
- social posts: a witness post near each grounded crime, plus chatter.

Places come only from the city pack's alias list (D-004). Times carry an explicit offset (the city's
UTC offset), so DuckDB, Spark and feeds.py all read the same instant.

Usage (the committed sample slice; never edit the files by hand):
    cd services/api && python -m app.feeds_gen --sample
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SEED = 42
REPORT_SHARE = 0.85          # share of grounded crimes that get a news report
REPORT_HOURS = (2, 90)       # report delay after the crime; q_news looks 4 days ahead
ROUNDUP_DAYS = 3             # two series crimes this close get a roundup article
# Off by default: a roundup corroborates a pair, and with today's renormalisation one corroborating item
# (0.39) LOWERS a strong pair's score (hero sample 0.787 -> 0.752). Scoring owners decide before this is on.
ROUNDUPS = False
NOISE_ARTICLES = 24
CHATTER_POSTS = 30

OUTLETS = ("The Coastal Chronicle", "Metro Daily", "City Express", "Evening Courier", "Neighbourhood Times")
PLATFORMS = ("x", "facebook", "instagram")

# Headline templates by crime sub-type. "{place}" is an alias as written locally.
HEADLINES: dict[str, tuple[str, ...]] = {
    "chain_snatching": ("Chain snatched from woman near {place}", "Bike-borne duo snatch chain at {place}",
                        "Robbery at {place}: woman loses gold chain to snatchers"),
    "mobile_snatching": ("Phone snatched from pedestrian at {place}", "Mobile robbery reported near {place}"),
    "street_robbery": ("Man robbed at knifepoint near {place}", "Street robbery at {place} late evening"),
    "cab_robbery": ("Cab driver robbed by passengers near {place}", "Night cab robbery reported at {place}"),
    "night_house_break": ("House break-in at {place}: grille cut, jewels stolen",
                          "Burglars target locked house near {place}"),
    "day_house_break": ("Daytime house break-in at {place}", "House burgled while family was out, {place}"),
    "two_wheeler_theft": ("Two-wheeler stolen from {place}",),
    "car_theft": ("Car stolen from residential street in {place}",),
}
ROUNDUP = ("Second {what} in days: {a} and {b} residents on edge", "Police link {what} cases in {a} and {b}")
ROUNDUP_WHAT = {"chain_snatching": "chain snatching", "night_house_break": "night burglary",
                "cab_robbery": "cab robbery"}
CIVIC = ("Traffic diversion on {place} for drain work", "Weekend market draws crowds at {place}",
         "Power shutdown planned in {place} on Saturday", "School sports day held at {place}",
         "Residents demand streetlights on {place}")
ELSEWHERE = ("Marina Beach", "Besant Nagar", "Kotturpuram", "Perungudi", "Sholinganallur")
WITNESS = ("Just saw two guys on a bike grab a chain near {place}. Be careful out there",
           "Police at {place} right now, someone got robbed?", "Heard shouting near {place}, cops arrived fast",
           "Break-in on our street in {place} last night. Lock your grilles")
CHATTER = ("Traffic crawling at {place} again", "Best filter coffee near {place}?", "Rain on the way, {place} flooded",
           "Festival lights up at {place}")


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _places(aliases: Sequence[Mapping[str, Any]], crime: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [a for a in aliases if a.get("station_id") and a["station_id"] == crime.get("station_id")]


def _tags(*words: str) -> list[str]:
    return ["#" + "".join(w.title().split()) for w in words if w]


def generate(
    crimes: Sequence[Mapping[str, Any]],
    aliases: Sequence[Mapping[str, Any]],
    grounded: Iterable[str],
    series: Sequence[Sequence[str]] = (),
    *,
    seed: int = SEED,
    roundups: bool = ROUNDUPS,
) -> tuple[list[dict], list[dict]]:
    """Articles and posts for the grounded crime ids. `crimes` rows need crime_id, station_id, sub_type and
    an aware `occurred_from`; `series` lists crime ids per series (for roundups)."""
    rnd = random.Random(seed)
    by_id = {c["crime_id"]: c for c in crimes}
    ids = sorted(i for i in set(grounded) if i in by_id)
    if not ids:
        return [], []
    tz = by_id[ids[0]]["occurred_from"].tzinfo
    articles: list[dict] = []
    posts: list[dict] = []

    def article(headline: str, places: list[str], at: datetime, body: str) -> None:
        n = len(articles) + 1
        articles.append({"article_id": f"NEWS-{n:05d}", "outlet": rnd.choice(OUTLETS), "published_at": _iso(at),
                         "headline": headline, "body": body, "places_mentioned": places,
                         "url": f"https://news.example.invalid/{n:05d}", "synthetic": True})

    def post(text: str, places: list[str], at: datetime, tags: list[str]) -> None:
        n = len(posts) + 1
        posts.append({"post_id": f"POST-{n:05d}", "platform": rnd.choice(PLATFORMS), "posted_at": _iso(at),
                      "handle": f"@resident{rnd.randrange(100, 999)}", "text": text, "places_mentioned": places,
                      "hashtags": tags or ["#Local"], "synthetic": True})

    # Grounded reports and witness posts.
    for cid in ids:
        c = by_id[cid]
        opts = _places(aliases, c)
        if not opts:
            continue  # no alias for this station: the feed cannot name it
        a = rnd.choice(opts)
        t0 = c["occurred_from"]
        if rnd.random() < REPORT_SHARE:
            at = t0 + timedelta(minutes=rnd.randrange(REPORT_HOURS[0] * 60, REPORT_HOURS[1] * 60))
            head = rnd.choice(HEADLINES.get(c.get("sub_type") or "", ("Crime reported near {place}",)))
            article(head.format(place=a["alias"]), [a["alias"]], at,
                    f"Police at {a['canonical']} are investigating. No arrests yet.")
        at = t0 + timedelta(minutes=rnd.randrange(10, 180))
        post(rnd.choice(WITNESS).format(place=a["alias"]), [a["alias"]], at, _tags(a["canonical"], "Alert"))

    # Roundups: consecutive crimes of one series close in time.
    if roundups:
        for members in series:
            ms = sorted((by_id[i] for i in members if i in by_id), key=lambda c: c["occurred_from"])
            for x, y in zip(ms, ms[1:]):
                gap = y["occurred_from"] - x["occurred_from"]
                px, py = _places(aliases, x), _places(aliases, y)
                if gap > timedelta(days=ROUNDUP_DAYS) or not px or not py or x["station_id"] == y["station_id"]:
                    continue
                at = y["occurred_from"] + timedelta(hours=rnd.randrange(3, 20))
                if at >= x["occurred_from"] + timedelta(days=4):
                    continue
                pa, pb = rnd.choice(px), rnd.choice(py)
                what = ROUNDUP_WHAT.get(y.get("sub_type") or "", "robbery")
                article(rnd.choice(ROUNDUP).format(what=what, a=pa["alias"], b=pb["alias"]),
                        sorted({pa["alias"], pb["alias"]}), at, "Police are checking whether the cases are linked.")

    # Noise across the grounded period.
    start = min(by_id[i]["occurred_from"] for i in ids) - timedelta(days=7)
    span = int((max(by_id[i]["occurred_from"] for i in ids) - start).total_seconds() // 60) + 14 * 24 * 60
    known = sorted({a["alias"] for a in aliases})
    for k in range(NOISE_ARTICLES):
        at = (start + timedelta(minutes=rnd.randrange(span))).astimezone(tz)
        if k % 3 == 2:
            place = rnd.choice(ELSEWHERE)
            article(f"Crowds gather at {place} for weekend event", [place], at, "Civic news.")
        else:
            place = rnd.choice(known)
            article(rnd.choice(CIVIC).format(place=place), [place], at, "Civic news.")
    for _ in range(CHATTER_POSTS):
        at = (start + timedelta(minutes=rnd.randrange(span))).astimezone(tz)
        place = rnd.choice(known)
        post(rnd.choice(CHATTER).format(place=place), [place], at, _tags(place))

    articles.sort(key=lambda r: (r["published_at"], r["article_id"]))
    posts.sort(key=lambda r: (r["posted_at"], r["post_id"]))
    return articles, posts


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------- the committed sample slice

def sample_inputs(sample_dir: Path) -> dict[str, Any]:
    """Crimes, aliases, grounded ids and series for the sample bundle: the judge cases, their series and
    decoys (data/sample/_truth), in city time."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    cols = ["crime_id", "station_id", "sub_type", "occurred_from"]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM read_parquet(?)",
                       [str(sample_dir / "sb" / "crimes.parquet")]).fetchall()
    manifest = json.loads((sample_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    series = json.loads((sample_dir / "_truth" / "series.json").read_text(encoding="utf-8"))
    decoys = json.loads((sample_dir / "_truth" / "decoys.json").read_text(encoding="utf-8"))
    offset = _city_offset()
    crimes = [dict(zip(cols, r)) for r in rows]
    for c in crimes:
        c["occurred_from"] = c["occurred_from"].astimezone(offset)
    judge = [s for s in series if s["series_id"] in manifest["judge_series"]]
    grounded = set(manifest["judge_ids"])
    for s in judge:
        grounded |= set(s["crime_ids"])
    for d in decoys:
        grounded |= set(d["crime_ids"])
    with open(sample_dir / "ref" / "place_aliases.csv", encoding="utf-8", newline="") as fh:
        aliases = list(csv.DictReader(fh))
    return {"crimes": crimes, "aliases": aliases, "grounded": sorted(grounded),
            "series": [s["crime_ids"] for s in judge]}


def _city_offset():
    from datetime import timezone

    from .adapters.zetaris_queries_n2 import city_time

    _, off = city_time()  # ("Asia/Kolkata", "+05:30") from the city pack
    sign = -1 if off.startswith("-") else 1
    h, m = (int(x) for x in off.lstrip("+-").split(":"))
    return timezone(sign * timedelta(hours=h, minutes=m))


def build_sample(sample_dir: Path) -> tuple[list[dict], list[dict]]:
    return generate(**sample_inputs(sample_dir))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", action="store_true", help="write data/sample/news and data/sample/social")
    args = ap.parse_args()
    if not args.sample:
        ap.error("only --sample is supported so far")
    from .config import get_settings

    d = get_settings().sample_dir
    arts, psts = build_sample(d)
    write_jsonl(d / "news" / "articles.jsonl", arts)
    write_jsonl(d / "social" / "posts.jsonl", psts)
    print(f"wrote {len(arts)} articles, {len(psts)} posts under {d}")
