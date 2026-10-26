"""Zetaris SQL for source onboarding (WS1-23): fixed templates over generated identifiers only.

A new source's CSV headers are text an uploader controls, so nothing here formats free text into SQL:
  - every Zetaris object is a generated name `onboard_<key>` / `onboard_<key>_raw` (IDENT), the key itself checked;
  - a source column name is used only after `check_header` accepted it (no backtick, quote, semicolon, newline or
    comment marker, a short safe character set, at most 64 characters), and then always backtick-quoted;
  - a mapped column's SQL comes from the fixed TRANSFORMS table, and its alias from the unified-field allowlist.
ZetarisClient.onboard() is the only caller, and it runs nothing that these functions did not build.
"""

from __future__ import annotations

import re
from typing import Iterable

from .dq_rules import DUP_MAX_DEG, DUP_WINDOW_MIN

KEY = re.compile(r"^[a-z0-9_]{3,30}$")
IDENT = re.compile(r"^onboard_[a-z0-9_]{1,40}(_raw)?$")
MAX_HEADER = 64
# Letters (any script), digits, space and a few punctuation marks real exports use in headers.
HEADER_OK = re.compile(r"^[\w .,/()&%:+#\-]+$", re.UNICODE)
HEADER_FORBIDDEN = ("`", "'", '"', ";", "\n", "\r", "--", "/*", "*/", "\\")
STAGE_ROOT = "/home/zetaris/customer-data/shared/nexus/onboard"

# The unified fields a column may map to (mirrors public.onboarding_fields; a test keeps them equal).
FIELDS = ("fir_no", "occurred_from", "occurred_to", "reported_at", "category", "sub_type", "sections_raw", "lat",
          "lon", "address", "narrative", "status")
REQUIRED = ("fir_no", "occurred_from", "category", "lat", "lon")

# transform -> SQL over one already-quoted column `c` (the only place SQL is written per column).
TRANSFORMS = {
    "none": "CAST(trim({c}) AS STRING)",
    "trim_upper": "upper(trim({c}))",
    # The export writes local times; Zetaris runs in GMT and stores instants, so read them in the city's zone.
    "date_dmy": "to_utc_timestamp(to_timestamp(trim({c}), 'dd/MM/yyyy'), '{tz}')",
    "datetime_dmy_hm": "to_utc_timestamp(to_timestamp(trim({c}), 'dd/MM/yyyy HH:mm'), '{tz}')",
    "latlong_lat": "CAST(trim(split({c}, ',')[0]) AS DOUBLE)",
    "latlong_lon": "CAST(trim(split({c}, ',')[1]) AS DOUBLE)",
}
NUMERIC_FIELDS = {"lat", "lon"}
TIME_FIELDS = {"occurred_from", "occurred_to", "reported_at"}


class OnboardRejected(ValueError):
    """The source cannot be onboarded as given (a bad header, key or mapping). The message is shown to the admin."""


# =====================
# Checks
# =====================


def check_key(key: str) -> str:
    if not isinstance(key, str) or not KEY.match(key):
        raise OnboardRejected("the source key must be 3-30 characters: a-z, 0-9 and _")
    return key


def ident(key: str, raw: bool = False) -> str:
    name = f"onboard_{check_key(key)}" + ("_raw" if raw else "")
    if not IDENT.match(name):
        raise OnboardRejected("generated object name is not valid")
    return name


def check_header(name: str) -> str:
    """Accept a CSV header for use as a quoted column name, or reject the whole source with a reason."""
    if not isinstance(name, str) or not name.strip():
        raise OnboardRejected("a column has an empty header")
    if len(name) > MAX_HEADER:
        raise OnboardRejected(f"a column header is longer than {MAX_HEADER} characters")
    for bad in HEADER_FORBIDDEN:
        if bad in name:
            raise OnboardRejected(f"column header {name[:40]!r} contains a character that is not allowed ({bad!r})")
    if name != name.strip() or not HEADER_OK.match(name):
        raise OnboardRejected(f"column header {name[:40]!r} contains characters that are not allowed")
    return name


def check_headers(names: Iterable[str]) -> list[str]:
    out = [check_header(n) for n in names]
    if len({n.lower() for n in out}) != len(out):
        raise OnboardRejected("two columns have the same header")
    if not out:
        raise OnboardRejected("the file has no columns")
    return out


def q(col: str) -> str:
    return f"`{check_header(col)}`"


# =====================
# Statement templates
# =====================


def stage_path(key: str) -> str:
    return f"{STAGE_ROOT}/{check_key(key)}/source.csv"


def create_raw(key: str) -> str:
    return (f'CREATE LIGHTNING FILESTORE TABLE {ident(key, raw=True)} FROM s3csv FORMAT CSV OPTIONS ('
            f'path "file://{stage_path(key)}", header "true", delimiter ",")')


def describe_raw(key: str) -> str:
    return f"DESCRIBE s3csv.{ident(key, raw=True)}"


def profile(key: str, columns: list[str]) -> str:
    """One row: total, then non-null and distinct counts per column (in column order)."""
    parts = ["count(*) AS n"]
    for i, c in enumerate(columns):
        parts += [f"count({q(c)}) AS nn{i}", f"count(DISTINCT {q(c)}) AS d{i}"]
    return f"SELECT {', '.join(parts)} FROM s3csv.{ident(key, raw=True)}"


def examples(key: str, columns: list[str], n: int = 5) -> str:
    cols = ", ".join(q(c) for c in columns)
    return f"SELECT {cols} FROM s3csv.{ident(key, raw=True)} LIMIT {int(n)}"


TZ = re.compile(r"^[A-Za-z]+(/[A-Za-z_]+){0,2}$")


def _select_list(mapping: list[dict], station_id: str, tz: str) -> list[str]:
    """`<transform SQL> AS <field>` per mapped column, plus the fixed station and source columns. `tz` is the city
    pack's time zone (e.g. Asia/Kolkata), checked."""
    if not re.match(r"^[A-Z0-9-]{3,40}$", station_id or ""):
        raise OnboardRejected("station id must be A-Z, 0-9 and -")
    if not TZ.match(tz or ""):
        raise OnboardRejected("bad time zone")
    seen: set[str] = set()
    cols = [f"'{station_id}' AS station_id"]
    for m in mapping:
        field = m.get("unified_field")
        if not field:
            continue
        if field not in FIELDS:
            raise OnboardRejected(f"unknown field {field!r}")
        if field in seen:
            raise OnboardRejected(f"field {field} is mapped more than once")
        seen.add(field)
        t = m.get("transform") or "none"
        if t not in TRANSFORMS:
            raise OnboardRejected(f"unknown transform {t!r}")
        cols.append(f"{TRANSFORMS[t].format(c=q(m['source_col']), tz=tz)} AS {field}")
    missing = [f for f in REQUIRED if f not in seen]
    if missing:
        raise OnboardRejected(f"required fields not mapped: {', '.join(missing)}")
    return cols


def mapped_select(key: str, mapping: list[dict], station_id: str, tz: str) -> str:
    return f"SELECT {', '.join(_select_list(mapping, station_id, tz))} FROM s3csv.{ident(key, raw=True)}"


def create_view(key: str, mapping: list[dict], station_id: str, tz: str) -> str:
    """The registered, NOT linked, source view in the nexus container (it is not part of v_crime_unified)."""
    return (f"CREATE OR REPLACE SCHEMASTORE VIEW {ident(key)} WITH CONTAINER nexus AS "
            f"{mapped_select(key, mapping, station_id, tz)}")


def count_view(key: str) -> str:
    return f"SELECT count(*) AS n FROM nexus.{ident(key)}"


def _mapped(mapping: list[dict]) -> set[str]:
    return {m["unified_field"] for m in mapping if m.get("unified_field")}


def dq(key: str, mapping: list[dict], station_id: str, tz: str, bounds: tuple[float, float, float, float]) -> str:
    """One row of DQ counts over the mapped rows, the same rules dq_rules applies to Nexus's own crimes:
    n, bad_date (unparseable or in the future), out_of_city (missing or outside the city-pack bounds), missing_required,
    repeated_fir_no (inside the file), ends_before_start, occurred_after_reported (0 when those fields are unmapped).
    `bounds` = (west, south, east, north)."""
    w, s, e, n = (float(x) for x in bounds)
    fields = _mapped(mapping)
    ends = ("sum(CASE WHEN occurred_to < occurred_from THEN 1 ELSE 0 END)" if "occurred_to" in fields else "0")
    after = ("sum(CASE WHEN reported_at < occurred_from THEN 1 ELSE 0 END)" if "reported_at" in fields else "0")
    base = mapped_select(key, mapping, station_id, tz)
    return ("SELECT count(*) AS n, "
            "sum(CASE WHEN occurred_from IS NULL OR occurred_from > current_timestamp() THEN 1 ELSE 0 END) AS bad_date, "
            f"sum(CASE WHEN lat IS NULL OR lon IS NULL OR lat < {s} OR lat > {n} OR lon < {w} OR lon > {e} "
            "THEN 1 ELSE 0 END) AS out_of_city, "
            "sum(CASE WHEN fir_no IS NULL OR fir_no = '' OR category IS NULL OR category = '' THEN 1 ELSE 0 END) "
            "AS missing_required, "
            "count(fir_no) - count(DISTINCT fir_no) AS repeated_fir_no, "
            f"{ends} AS ends_before_start, {after} AS occurred_after_reported "
            f"FROM ({base}) m")


def dq_samples(key: str, mapping: list[dict], station_id: str, tz: str,
               bounds: tuple[float, float, float, float]) -> str:
    """Up to 20 failing rows (fir_no and which rule), for the review screen."""
    w, s, e, n = (float(x) for x in bounds)
    base = mapped_select(key, mapping, station_id, tz)
    return ("SELECT coalesce(nullif(fir_no, ''), '(no FIR number)') AS fir_no, CASE "
            "WHEN occurred_from IS NULL OR occurred_from > current_timestamp() THEN 'bad_date' "
            f"WHEN lat IS NULL OR lon IS NULL OR lat < {s} OR lat > {n} OR lon < {w} OR lon > {e} THEN 'out_of_city' "
            "ELSE 'missing_required' END AS rule "
            f"FROM ({base}) m WHERE occurred_from IS NULL OR occurred_from > current_timestamp() "
            f"OR lat IS NULL OR lon IS NULL OR lat < {s} OR lat > {n} OR lon < {w} OR lon > {e} "
            "OR fir_no IS NULL OR fir_no = '' OR category IS NULL OR category = '' ORDER BY fir_no LIMIT 20")


def date_range(key: str, mapping: list[dict], station_id: str, tz: str) -> str:
    """The file's first and last occurrence (UTC), read before likely_duplicates so its sb.crimes range is literal."""
    base = mapped_select(key, mapping, station_id, tz)
    return ("SELECT CAST(min(occurred_from) AS STRING) AS lo, CAST(max(occurred_from) AS STRING) AS hi "
            f"FROM ({base}) m WHERE occurred_from IS NOT NULL")


def _ts_literal(value: str, days: int = 0) -> str:
    """A checked TIMESTAMP literal from a Zetaris timestamp string, shifted by `days` here (an expression on the
    literal in SQL would not be pushed down). No free text reaches SQL."""
    from datetime import datetime, timedelta

    dt = datetime.fromisoformat(str(value).strip().replace(" ", "T")[:19]) + timedelta(days=days)
    return f"TIMESTAMP '{dt.strftime('%Y-%m-%d %H:%M:%S')}'"


def likely_duplicates(key: str, mapping: list[dict], station_id: str, tz: str, lo: str, hi: str) -> str:
    """New rows that look like a crime Nexus already holds, with dq_rules' thresholds (DUP_MAX_DEG, ~275 m).
    Time: within DUP_WINDOW_MIN minutes when the file gives a time of occurrence; when it gives a date only, any time
    that day (a window from that midnight, not a date equality). Category is NOT compared: the export uses its own
    crime heads, so these are reported at info severity, "category not compared". `lo`/`hi` come from date_range()
    and are rendered as TIMESTAMP literals, so the sb.crimes range is a pushed-down filter (EXPLAIN: PushedFilters on
    occurred_from), not a join condition."""
    timed = any(m.get("unified_field") == "occurred_from" and m.get("transform") == "datetime_dmy_hm" for m in mapping)
    if timed:
        window = f"abs(unix_timestamp(c.occurred_from) - unix_timestamp(m.occurred_from)) <= {int(DUP_WINDOW_MIN) * 60}"
    else:
        window = "c.occurred_from >= m.occurred_from AND c.occurred_from < m.occurred_from + INTERVAL 1 DAY"
    deg = float(DUP_MAX_DEG)
    base = mapped_select(key, mapping, station_id, tz)
    return ("WITH m AS (" + base + "), "
            f"c AS (SELECT crime_id, occurred_from, lat, lon FROM sb.crimes WHERE occurred_from >= {_ts_literal(lo, -1)} "
            f"AND occurred_from < {_ts_literal(hi, 2)}) "
            "SELECT m.fir_no, c.crime_id FROM m JOIN c "
            f"ON {window} AND abs(c.lat - m.lat) <= {deg} AND abs(c.lon - m.lon) <= {deg} "
            "ORDER BY m.fir_no, c.crime_id LIMIT 200")
