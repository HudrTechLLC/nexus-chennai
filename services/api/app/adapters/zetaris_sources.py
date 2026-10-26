"""Where Zetaris finds the crime data: hosted Supabase, or files in Zetaris's own store (WS1-19).

One map, read by both the named-query registry (ZetarisClient) and zetaris/register.py (the
`{{src:sb}}` / `{{src:nexus}}` placeholders in zetaris/*.sql), so the two paths cannot drift.

- `supabase` (default): the `sb` JDBC datasource on our Supabase, and views in container `nexus`.
- `files`: the Parquet file-store database `nexus_fs` (the same table names, columns and Spark types
  as the sb objects, built by `python -m data.setup_live`), and views in container `nexusfs`. This
  needs only a local Zetaris, so a judge can reproduce live mode with their own instance. On our box the
  files path sits in its own database and container, so it never re-points the live `nexus` views.

Select with the environment variable ZETARIS_DATA (settings.zetaris_data). No third-party imports:
register.py and stage_files.py load this file by path.

ZETARIS_FILES_SUFFIX (letters/digits, default empty) gives the files path its own names: database
nexus_fs<sfx>, container nexusfs<sfx>, staging folder fs<sfx>. It lets a second copy (a clean-machine
rehearsal) sit beside the first without touching it. Empty = the names above, unchanged.
"""

from __future__ import annotations

import os
import re

SOURCES: dict[str, dict[str, str]] = {
    "supabase": {"sb": "sb", "nexus": "nexus", "fsdir": "fs"},
    "files": {"sb": "nexus_fs", "nexus": "nexusfs", "fsdir": "fs"},
}
SUFFIX_ENV = "ZETARIS_FILES_SUFFIX"
DEFAULT = "supabase"

# The sb objects the named queries and views read; `files` mode has one nexus_fs table for each.
FILE_TABLES = ("crimes", "statements", "crime_vehicles", "evidence_media", "forensics", "crime_features_v",
               "tips_v", "section_map", "stations", "link_alerts", "case_bundle_v")

# Dot-qualified names only: `sb.x` and `nexus.x` (never `nexus_feeds.x`, never a path segment).
_QUALIFIED = re.compile(r"\b(sb|nexus)\.(?=[A-Za-z_])")


def files_suffix() -> str:
    sfx = os.environ.get(SUFFIX_ENV, "")
    if not re.fullmatch(r"[a-z0-9]{0,8}", sfx):
        raise ValueError(f"{SUFFIX_ENV} must be up to 8 lower-case letters or digits, not {sfx!r}")
    return sfx


def sources(data: str | None) -> dict[str, str]:
    key = data or DEFAULT
    if key not in SOURCES:
        raise ValueError(f"ZETARIS_DATA must be one of {sorted(SOURCES)}, not {key!r}")
    if key != "files":
        return SOURCES[key]
    sfx = files_suffix()
    return {k: v + sfx for k, v in SOURCES["files"].items()}


def localise(sql: str, data: str | None) -> str:
    """Rewrite `sb.` and `nexus.` prefixes in a named query's Lightning SQL for the chosen data source.
    For `supabase` the text comes back unchanged."""
    m = sources(data)
    if m["sb"] == "sb" and m["nexus"] == "nexus":
        return sql
    return _QUALIFIED.sub(lambda g: m[g.group(1)] + ".", sql)
