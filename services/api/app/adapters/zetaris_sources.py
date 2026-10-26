"""Where Zetaris finds the crime data: hosted Supabase, or files in Zetaris's own store (WS1-19).

One map, read by both the named-query registry (ZetarisClient) and zetaris/register.py (the
`{{src:sb}}` / `{{src:nexus}}` placeholders in zetaris/*.sql), so the two paths cannot drift.

- `supabase` (default): the `sb` JDBC datasource on our Supabase, and views in container `nexus`.
- `files`: the Parquet file-store database `nexus_fs` (the same table names, columns and Spark types
  as the sb objects, built by `python -m data.setup_live`), and views in container `nexusfs`. This
  needs only a local Zetaris, so a judge can reproduce live mode with their own instance. On our box the
  files path sits in its own database and container, so it never re-points the live `nexus` views.

Select with the environment variable ZETARIS_DATA (settings.zetaris_data). No third-party imports:
register.py loads this file by path.
"""

from __future__ import annotations

import re

SOURCES: dict[str, dict[str, str]] = {
    "supabase": {"sb": "sb", "nexus": "nexus"},
    "files": {"sb": "nexus_fs", "nexus": "nexusfs"},
}
DEFAULT = "supabase"

# The sb objects the named queries and views read; `files` mode has one nexus_fs table for each.
FILE_TABLES = ("crimes", "statements", "crime_vehicles", "evidence_media", "forensics", "crime_features_v",
               "tips_v", "section_map", "stations", "link_alerts", "case_bundle_v")

# Dot-qualified names only: `sb.x` and `nexus.x` (never `nexus_feeds.x`, never a path segment).
_QUALIFIED = re.compile(r"\b(sb|nexus)\.(?=[A-Za-z_])")


def sources(data: str | None) -> dict[str, str]:
    key = data or DEFAULT
    if key not in SOURCES:
        raise ValueError(f"ZETARIS_DATA must be one of {sorted(SOURCES)}, not {key!r}")
    return SOURCES[key]


def localise(sql: str, data: str | None) -> str:
    """Rewrite `sb.` and `nexus.` prefixes in a named query's Lightning SQL for the chosen data source.
    For `supabase` the text comes back unchanged."""
    m = sources(data)
    if m == SOURCES["supabase"]:
        return sql
    return _QUALIFIED.sub(lambda g: m[g.group(1)] + ".", sql)
