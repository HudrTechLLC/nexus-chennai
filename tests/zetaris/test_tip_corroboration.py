"""q_tip_corroboration: screened tips in the crime's H3 r8 cell within :days; never unscreened or quarantined."""

import duckdb

from app.adapters.zetaris import NAMED_QUERIES, NamedQuery, ZetarisClient
from app.config import Settings
from app.tracing import Tracer

CRIMES = """SELECT * FROM (VALUES ('C-1', '88aa', '2026-W42', TIMESTAMPTZ '2026-10-14 14:10:00+00'))
  t(crime_id, h3_r8, week, occurred_from)"""
TIPS = """SELECT * FROM (VALUES
 ('TIP-A', '88aa', '2026-W43', 'screened', '{"summary": "Tip mentions: red, motorcycle.", "tags": ["red"], "verdict": "clean"}', 'vehicle_seen', 'web'),
 ('TIP-B', '88aa', '2026-W43', 'new', NULL, 'vehicle_seen', 'web'),
 ('TIP-C', '88aa', '2026-W43', 'quarantined', '{"summary": "x", "tags": [], "verdict": "injection"}', 'something_else', 'web'),
 ('TIP-D', '88bb', '2026-W43', 'screened', '{"summary": "y", "tags": [], "verdict": "clean"}', 'person_seen', 'web'),
 ('TIP-E', '88aa', '2026-W49', 'screened', '{"summary": "late", "tags": [], "verdict": "clean"}', 'person_seen', 'web'),
 ('TIP-F', '88aa', '2026-W41', 'reviewed', '{"summary": "early", "tags": [], "verdict": "clean"}', 'person_seen', 'web')
) t(tip_id, approx_cell, received_week, status, guard, category, channel)"""


def _client(tmp_path):
    d = tmp_path / "sample"
    (d / "sb").mkdir(parents=True)
    con = duckdb.connect()
    con.execute(f"COPY ({CRIMES}) TO '{(d / 'sb' / 'crimes.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY ({TIPS}) TO '{(d / 'sb' / 'tips.parquet').as_posix()}' (FORMAT PARQUET)")
    q = NAMED_QUERIES["q_tip_corroboration"]
    c = ZetarisClient(Settings(_env_file=None, sample_mode=True, zetaris_api_key=""),
                      tracer=Tracer("t", tmp_path, echo=False), registry={q.name: q})
    c._duck = duckdb.connect(":memory:")
    c._duck.execute(f"SET file_search_path = '{d.as_posix()}'")
    return c


def test_only_screened_tips_in_cell_and_window(tmp_path):
    rows = _client(tmp_path).named("q_tip_corroboration", agent="Linker", crime_id="C-1").dicts()
    assert [r["tip_id"] for r in rows] == ["TIP-A"]  # B unscreened, C quarantined, D other cell, E too late, F too early
    r = rows[0]
    assert r["summary"] == "Tip mentions: red, motorcycle." and r["verdict"] == "clean" and r["tags"] == '["red"]'


def test_days_default_and_override(tmp_path):
    c = _client(tmp_path)
    assert [r["tip_id"] for r in c.named("q_tip_corroboration", agent="T", crime_id="C-1", days=60).dicts()] \
        == ["TIP-A", "TIP-E"]


def test_live_form_never_selects_text_and_filters_status():
    sql = NAMED_QUERIES["q_tip_corroboration"].lightning
    assert "t.text" not in sql and "sb.tips_v" in sql and "'new'" not in sql and "quarantined" not in sql
    assert NAMED_QUERIES["q_tip_corroboration"].defaults == {"days": 30}
    assert isinstance(NAMED_QUERIES["q_tip_corroboration"], NamedQuery)
