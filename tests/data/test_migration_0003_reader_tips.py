"""zetaris_reader must not read tip text, the passphrase hash or contact-ish flags."""

import re
from pathlib import Path

SQL = (Path(__file__).resolve().parents[2] / "supabase/migrations/0003_zetaris_reader_tips.sql").read_text(encoding="utf-8")
CODE = re.sub(r"--[^\n]*", "", SQL.lower())


def test_revokes_whole_table_then_grants_safe_columns():
    assert "revoke select on public.tips from zetaris_reader" in CODE
    cols = re.search(r"grant select \(([^)]*)\)\s+on public\.tips to zetaris_reader", CODE, flags=re.S).group(1)
    granted = {c.strip() for c in cols.split(",")}
    assert {"text", "tip_code_hash", "follow_up_enabled"}.isdisjoint(granted)
    assert {"tip_id", "guard", "approx_cell", "received_week"} <= granted
    assert "tip_media" not in CODE.split("revoke")[0] and "grant select on public.tip_media" not in CODE
