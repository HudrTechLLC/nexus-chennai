"""Ask Nexus (WS3-30): a plain-English question answered from named registry queries.

The model never writes SQL and never writes the answer. Nemotron Lightning (fast lane) turns the question into a
small JSON *plan* (category, sub type, stations by name, case status, a time window, hours of day, words to find
in the FIR). Code then checks every field against fixed vocabularies, resolves station names to ids from the city
pack and time phrases to dates in city time, runs `q_search` through Zetaris (rule R1), applies the plan's filters
in code and writes a templated answer: crime ids, a reason per row, and a summary built from the rows. Anything
that does not resolve makes the question `unmappable` with the specific reason; no filter is silently dropped.

Not part of the agent graph: linking, scoring and the judge path never call this module.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .adapters.zetaris_queries_n2 import search_params
from .agents.base import AgentDeps, AgentError, chat_json, rows_as_dicts
from .agents.series import is_test_fir

AGENT = "Ask"
QUERY = "q_search"  # the only query a plan may use for now (allow-list)
QUERY_LIMIT = 1000  # q_search has no LIMIT; a full page is reported as "at least"
MAX_ROWS = 50  # rows kept in the answer, newest first
MAX_STATIONS = 3
MAX_WORDS = 4
DEFAULT_DAYS = 90
CITY = Path(__file__).resolve().parents[3] / "cities" / "chennai"
TZ = ZoneInfo("Asia/Kolkata")

CATEGORIES: dict[str, list[str]] = {
    "robbery": ["chain_snatching", "mobile_snatching", "street_robbery", "cab_robbery"],
    "theft": ["two_wheeler_theft", "pickpocket", "shop_theft", "car_theft"],
    "house_break": ["night_house_break", "day_house_break"],
    "hurt": ["assault", "attempt_murder"],
    "cheating": ["cheating"],
    "crimes_against_women": ["stalking"],
    "homicide": ["murder"],
    "kidnapping": ["kidnapping"],
}
SUB_TYPES = {s: c for c, subs in CATEGORIES.items() for s in subs}
STATUSES = {"registered": "registered", "under_investigation": "under investigation", "undetected": "undetected",
            "charge_sheeted": "charge sheet filed", "closed": "closed"}
TIME_KINDS = ("today", "yesterday", "this_week", "this_month", "last_month", "last_days", "since", "between")
WORD = re.compile(r"^[a-z0-9]{3,20}$")
UNMAPPABLE_HELP = ("I can only search crimes by type, police station area, time, case status and words written in "
                   "the FIR.")
TEST_FOOTNOTE = "test filings excluded"


# ---------------------------------------------------------------------------- vocabulary


def _station_name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_stations(city: Path = CITY) -> dict[str, tuple[str, str]]:
    """{normalised place name: (station_id, station name)} from the city pack (stations + place aliases)."""
    out: dict[str, tuple[str, str]] = {}
    by_code: dict[str, tuple[str, str]] = {}
    with open(city / "stations_seed.csv", encoding="utf8") as f:
        for r in csv.DictReader(f):
            sid = f"PS-{_station_name_key(r['name']).upper()}-{r['code']}"
            by_code[r["code"]] = (sid, r["name"])
            out[_station_name_key(r["name"])] = (sid, r["name"])
    alias_file = city / "place_aliases.csv"
    if alias_file.exists():
        with open(alias_file, encoding="utf8") as f:
            for r in csv.DictReader(f):
                hit = by_code.get((r.get("station_code") or "").strip())
                if hit:
                    out.setdefault(_station_name_key(r["alias"]), hit)
                    out.setdefault(_station_name_key(r.get("canonical") or ""), hit)
    out.pop("", None)
    return out


STATIONS = load_stations()
STATION_NAMES = sorted({name for _, name in STATIONS.values()})


# ---------------------------------------------------------------------------- the model's part

PROMPT = """You turn a police analyst's question about crimes in Chennai into a JSON search plan. You never answer the
question and never write SQL. Use ONLY these values:

category and its sub_types (pick the category the sub_type is listed under):
{categories}
status: {statuses}
stations: police station areas by NAME, e.g. Adyar, Velachery, Anna Nagar (at most 3)
time: one of
  {{"kind":"today"}} {{"kind":"yesterday"}} {{"kind":"this_week"}} {{"kind":"this_month"}} {{"kind":"last_month"}}
  {{"kind":"last_days","days":N}}  {{"kind":"since","date":"YYYY-MM-DD"}}
  {{"kind":"between","from":"YYYY-MM-DD","to":"YYYY-MM-DD"}}  or null when no time is given
hours: hours of day in 24 h, {{"from":H,"to":H}} (to is exclusive; "after 7 pm" = from 19 to 24; "night" = from 22
  to 6), or null
words: up to 4 single lowercase words that must appear in the FIR text: vehicle, colour, brand, item, weapon
  (e.g. "red", "pulsar"). Never put category, place, time or status words here.

Today is {today}. Reply with ONE JSON object and nothing else:
{{"answerable": true, "category": null, "sub_type": null, "stations": [], "status": null, "time": null,
  "hours": null, "words": []}}
If the question is not a search for crimes (people, predictions, advice, anything else), reply
{{"answerable": false}}."""


def plan_messages(question: str, today: date) -> list[dict[str, str]]:
    cats = "\n".join(f"  {c}: {', '.join(subs)}" for c, subs in CATEGORIES.items())
    system = PROMPT.format(categories=cats,
                           statuses=", ".join(STATUSES), today=today.isoformat())
    return [{"role": "system", "content": system}, {"role": "user", "content": question.strip()}]


# ---------------------------------------------------------------------------- code's part: check and resolve


class Unmappable(Exception):
    """The question cannot be mapped to registry queries; the message is shown to the analyst as is."""


@dataclass
class Plan:
    category: str = ""
    sub_type: str = ""
    stations: list[tuple[str, str]] = field(default_factory=list)  # (station_id, name)
    status: str = ""
    since: date | None = None
    until: date | None = None  # exclusive
    time_label: str = ""
    hours: tuple[int, int] | None = None
    words: list[str] = field(default_factory=list)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _parse_date(v: Any, what: str) -> date:
    try:
        return date.fromisoformat(str(v))
    except ValueError as exc:
        raise Unmappable(f"I could not read the date {v!r} ({what}).") from exc


def resolve_time(t: Any, today: date) -> tuple[date, date, str]:
    """(since, until exclusive, label) in city dates. No time given: the last 90 days, said so in the label."""
    end = today + timedelta(days=1)
    if not t:
        return today - timedelta(days=DEFAULT_DAYS - 1), end, f"last {DEFAULT_DAYS} days (no time given)"
    if not isinstance(t, dict) or t.get("kind") not in TIME_KINDS:
        raise Unmappable("I could not work out the time window; say e.g. \"this month\" or \"last 30 days\".")
    k = t["kind"]
    if k == "today":
        return today, end, "today"
    if k == "yesterday":
        return today - timedelta(days=1), today, "yesterday"
    if k == "this_week":
        start = today - timedelta(days=today.weekday())
        return start, end, f"this week (from {start:%d %b})"
    if k == "this_month":
        return _month_start(today), end, f"this month ({today:%B %Y})"
    if k == "last_month":
        start = _month_start(_month_start(today) - timedelta(days=1))
        return start, _month_start(today), f"last month ({start:%B %Y})"
    if k == "last_days":
        try:
            n = int(t.get("days"))
        except (TypeError, ValueError) as exc:
            raise Unmappable("I could not read how many days back to look.") from exc
        if not 1 <= n <= 730:
            raise Unmappable("I can look back between 1 day and 2 years.")
        return today - timedelta(days=n - 1), end, f"last {n} days"
    if k == "since":
        start = _parse_date(t.get("date"), "since")
        if start > today:
            raise Unmappable("That start date is in the future.")
        return start, end, f"since {start:%d %b %Y}"
    start, stop = _parse_date(t.get("from"), "from"), _parse_date(t.get("to"), "to")
    if stop < start:
        raise Unmappable("The time window ends before it starts.")
    return start, stop + timedelta(days=1), f"{start:%d %b %Y} to {stop:%d %b %Y}"


def _hour_label(h: int) -> str:
    h %= 24
    return "midnight" if h == 0 else "noon" if h == 12 else f"{h % 12} {'am' if h < 12 else 'pm'}"


def resolve_plan(raw: dict[str, Any], today: date) -> Plan:
    """Check every field of the model's plan; raise Unmappable with the specific reason."""
    if raw.get("answerable") is False:
        raise Unmappable(UNMAPPABLE_HELP)
    p = Plan()
    cat, sub, status = (str(raw.get(k) or "").strip().lower() for k in ("category", "sub_type", "status"))
    if sub:
        if sub not in SUB_TYPES:
            raise Unmappable(f"I don't know the crime type \"{sub.replace('_', ' ')}\".")
        # The sub type names exactly one category, so a mismatched category is a slip, not a second filter:
        # the category is read from the sub type (fixed vocabulary, nothing guessed).
        cat = SUB_TYPES[sub]
    if cat and cat not in CATEGORIES:
        raise Unmappable(f"I don't know the crime type \"{cat.replace('_', ' ')}\".")
    if status and status not in STATUSES:
        raise Unmappable(f"I don't know the case status \"{status.replace('_', ' ')}\".")
    p.category, p.sub_type, p.status = cat, sub, status

    names = raw.get("stations") or []
    if not isinstance(names, list):
        names = [names]
    if len(names) > MAX_STATIONS:
        raise Unmappable(f"I can search at most {MAX_STATIONS} station areas at once.")
    for n in names:
        hit = STATIONS.get(_station_name_key(str(n)))
        if hit is None:
            raise Unmappable(f"I don't know a police station area called \"{n}\"; name a station, e.g. Adyar.")
        if hit not in p.stations:
            p.stations.append(hit)

    p.since, p.until, p.time_label = resolve_time(raw.get("time"), today)

    hours = raw.get("hours")
    if hours:
        try:
            h0, h1 = int(hours.get("from")), int(hours.get("to"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise Unmappable("I could not read the hours of day.") from exc
        if not (0 <= h0 <= 23 and 0 <= h1 <= 24) or h0 == h1 % 24:
            raise Unmappable("I could not read the hours of day.")
        p.hours = (h0, h1)

    blocked = set(CATEGORIES) | set(SUB_TYPES) | set(STATIONS) | {"crime", "crimes", "case", "cases"}
    words = []
    for w in raw.get("words") or []:
        w = str(w).strip().lower()
        if not WORD.match(w):
            raise Unmappable(f"I can only look for single plain words in the FIR text, not \"{w}\".")
        if w not in blocked and w not in words:
            words.append(w)
    if len(words) > MAX_WORDS:
        raise Unmappable(f"Too many words to look for; keep it to {MAX_WORDS}.")
    p.words = words

    if not (p.category or p.stations or p.words or p.status):
        raise Unmappable("That is too broad: name a crime type, a station area, a case status or something "
                         "written in the FIR.")
    return p


PLURAL = {"robbery": "robberies", "theft": "thefts", "house_break": "house breaks", "hurt": "hurt cases",
          "cheating": "cheating cases", "crimes_against_women": "crimes against women", "homicide": "homicides",
          "kidnapping": "kidnappings", "chain_snatching": "chain snatchings", "mobile_snatching": "mobile snatchings",
          "street_robbery": "street robberies", "cab_robbery": "cab robberies", "two_wheeler_theft": "two-wheeler thefts",
          "pickpocket": "pickpocketing cases", "shop_theft": "shop thefts", "car_theft": "car thefts",
          "night_house_break": "night house breaks", "day_house_break": "day house breaks", "assault": "assaults",
          "attempt_murder": "attempted murders", "stalking": "stalking cases", "murder": "murders"}


def plural(kind: str) -> str:
    return PLURAL.get(kind, kind.replace("_", " ") + "s")


def understood(p: Plan) -> str:
    bits = [plural(p.sub_type or p.category) if (p.sub_type or p.category) else "crimes"]
    if p.stations:
        bits.append("at " + " / ".join(name for _, name in p.stations))
    if p.status:
        bits.append(STATUSES[p.status])
    if p.words:
        bits.append("FIR mentions " + " + ".join(p.words))
    if p.hours:
        bits.append(f"between {_hour_label(p.hours[0])} and {_hour_label(p.hours[1])}")
    bits.append(p.time_label)
    return ", ".join(bits)


# ---------------------------------------------------------------------------- filters (in code, over q_search rows)


def _hour(row: dict[str, Any]) -> int | None:
    m = re.match(r"\d{4}-\d{2}-\d{2}[T ](\d{2})", str(row.get("occurred_from") or ""))
    return int(m.group(1)) if m else None


def in_hours(h: int | None, hours: tuple[int, int]) -> bool:
    if h is None:
        return False
    h0, h1 = hours
    return h0 <= h < h1 if h0 < h1 else (h >= h0 or h < h1 % 24)


def has_words(row: dict[str, Any], words: list[str]) -> bool:
    text = f"{row.get('text') or ''} {row.get('address') or ''}".lower()
    return all(re.search(rf"(^|[^a-z0-9]){re.escape(w)}", text) for w in words)


def filter_list(p: Plan) -> list[dict[str, Any]]:
    out = []
    if p.sub_type:
        out.append({"field": "sub_type", "op": "=", "value": p.sub_type, "label": p.sub_type.replace("_", " ")})
    if p.words:
        out.append({"field": "text", "op": "has all", "value": p.words,
                    "label": "FIR mentions " + " + ".join(p.words)})
    if p.hours:
        out.append({"field": "hour", "op": "between", "value": list(p.hours),
                    "label": f"{_hour_label(p.hours[0])} to {_hour_label(p.hours[1])}"})
    out.append({"field": "narrative", "op": "not test filing", "value": "D-033", "label": TEST_FOOTNOTE})
    return out


# ---------------------------------------------------------------------------- the answer (templated)


def _when(row: dict[str, Any]) -> str:
    try:
        return datetime.fromisoformat(str(row["occurred_from"])).strftime("%d %b %Y %H:%M")
    except (KeyError, ValueError):
        return "time unknown"


def why(row: dict[str, Any], p: Plan) -> str:
    kind = (row.get("sub_type") or row.get("category") or "crime").replace("_", " ")
    station = re.sub(r"^PS-|-[A-Z]\d+$", "", str(row.get("station_id") or "")).title()
    bits = [f"{kind} at {station}, {_when(row)}"]
    if p.words:
        bits.append("FIR mentions " + " + ".join(p.words))
    if p.status:
        bits.append(STATUSES[p.status])
    return "; ".join(bits)


def summary(total: int, truncated: bool, rows: list[dict[str, Any]], p: Plan, excluded: int) -> str:
    u = understood(p)
    if total == 0:
        s = f"No cases match: {u}."
    else:
        n = f"At least {total}" if truncated else str(total)
        s = f"{n} {'case matches' if total == 1 else 'cases match'}: {u}. Newest {_when(rows[0])}."
        if total > len(rows):
            s += f" Showing the newest {len(rows)}."
    if excluded:
        s += f" ({excluded} test {'filing' if excluded == 1 else 'filings'} excluded.)"
    return s


# ---------------------------------------------------------------------------- one question, end to end


@dataclass
class Outcome:
    status: str  # answered | unmappable | failed
    plan: dict[str, Any] | None
    answer: dict[str, Any] | None
    model: str | None = None
    routed_model: str | None = None
    receipt_id: str | None = None
    error: str | None = None


def answer_question(question: str, deps: AgentDeps, today: date | None = None,
                    on_running: Any = None) -> Outcome:
    """Plan (model) -> check (code) -> run named queries (Zetaris) -> filter and answer (code)."""
    today = today or datetime.now(TZ).date()
    deps.tracer.emit(AGENT, "ask_question", input_summary=question[:120], status="ok")
    try:
        raw, result = chat_json(deps, "fast", plan_messages(question, today), agent=AGENT, purpose="ask plan",
                                thinking=False, expect="answerable", temperature=0, max_tokens=500)
    except AgentError as exc:
        deps.tracer.emit(AGENT, "ask_failed", output_summary=str(exc)[:300], status="error")
        return Outcome("failed", None, None, error=f"The planning model did not answer: {str(exc)[:200]}")
    model = dict(model=getattr(result, "model", None), routed_model=getattr(result, "routed_model", None),
                 receipt_id=getattr(result, "receipt_id", None))
    deps.tracer.emit(AGENT, "plan", input_summary=question[:120], output_summary=str(raw)[:300],
                     model=model["model"], status="ok")
    try:
        p = resolve_plan(raw, today)
    except Unmappable as exc:
        deps.tracer.emit(AGENT, "ask_unmappable", output_summary=str(exc), status="ok")
        return Outcome("unmappable", {"steps": [], "filters": [], "understood": None, "model_plan": raw},
                       {"summary": str(exc), "total": 0, "truncated": False, "rows": []}, **model)

    if on_running:
        on_running()
    steps, rows, truncated = [], [], False
    for sid, name in (p.stations or [("", "")]):
        params = search_params(" ".join(p.words), {"category": p.category, "station_id": sid, "status": p.status,
                                                   "since": p.since.isoformat(), "until": p.until.isoformat()})
        try:
            res = deps.zetaris.named(QUERY, agent=AGENT, limit=QUERY_LIMIT, **params)
        except Exception as exc:  # noqa: BLE001 - one failed query fails the question, with the reason
            deps.tracer.emit(AGENT, "ask_failed", input_summary=QUERY, output_summary=str(exc)[:300], status="error")
            return Outcome("failed", {"steps": steps, "filters": filter_list(p), "understood": understood(p)}, None,
                           error=f"The registry query failed: {str(exc)[:200]}", **model)
        got = rows_as_dicts(res)
        truncated = truncated or len(got) >= QUERY_LIMIT
        what = plural(p.sub_type or p.category) if (p.sub_type or p.category) else "crimes"
        steps.append({"query": QUERY, "params": params, "query_id": res.query_id, "rows": len(got),
                      "purpose": f"Find {what}" + (f" at {name}" if name else "") + f", {p.time_label}"})
        rows += got

    seen, kept, excluded = set(), [], 0
    for r in rows:
        cid = r.get("crime_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        if p.sub_type and r.get("sub_type") != p.sub_type:
            continue
        if p.words and not has_words(r, p.words):
            continue
        if p.hours and not in_hours(_hour(r), p.hours):
            continue
        if is_test_fir(r.get("text")):
            excluded += 1
            continue
        kept.append(r)
    kept.sort(key=lambda r: (str(r.get("occurred_from") or ""), str(r["crime_id"])), reverse=True)
    shown = kept[:MAX_ROWS]
    answer = {"summary": summary(len(kept), truncated, shown, p, excluded), "total": len(kept),
              "truncated": truncated, "excluded_test_filings": excluded,
              "rows": [{"crime_id": r["crime_id"], "why": why(r, p)} for r in shown]}
    deps.tracer.emit(AGENT, "ask_answered", input_summary=understood(p)[:200],
                     output_summary=f"{len(kept)} rows{' (truncated)' if truncated else ''}; {excluded} test excluded",
                     zetaris_query_ids=[s["query_id"] for s in steps], status="ok")
    plan = {"steps": steps, "filters": filter_list(p), "understood": understood(p), "model_plan": raw}
    return Outcome("answered", plan, answer, **model)
