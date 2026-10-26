"""zetaris/10_views.sql and the sample bundle's views.sql expose the same v_crime_unified columns."""

import re
from pathlib import Path

from data.generator.sample import UNIFIED_COLUMNS
from zetaris.register import statements

ROOT = Path(__file__).resolve().parents[2]


def _select_columns(sql: str) -> list[str]:
    """Columns of the view's first branch: the SELECT that starts with crime_id (after any CTEs).
    The other branches must match it positionally; DuckDB's DESCRIBE in test_sample_bundle and the live
    count check in 10_views.sql catch a width mismatch."""
    body = re.search(r"SELECT\s+(crime_id,.*?)\bFROM\b", sql, re.S).group(1)
    return [re.split(r"\s+AS\s+", c.strip(), flags=re.I)[-1].strip() for c in body.split(",")]


def test_live_view_columns_match_the_sample_view():
    stmts = statements((ROOT / "zetaris" / "10_views.sql").read_text(encoding="utf-8"))
    view = next(s for s in stmts if "VIEW v_crime_unified" in s)
    assert "WITH CONTAINER nexus" in view
    assert _select_columns(view.split(" AS\n", 1)[1]) == UNIFIED_COLUMNS
    sample = (ROOT / "data" / "sample" / "views.sql").read_text(encoding="utf-8")
    assert _select_columns(sample.split("AS\n", 1)[1]) == UNIFIED_COLUMNS
