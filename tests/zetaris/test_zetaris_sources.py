"""One source map for crime data (WS1-19): hosted Supabase (`sb`, container `nexus`) or the Zetaris file
store (`nexus_fs`, container `nexusfs`). The registry and zetaris/register.py both read it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from app.adapters.zetaris import NAMED_QUERIES, ZetarisClient
from app.adapters.zetaris_sources import FILE_TABLES, SOURCES, localise, sources
from app.config import Settings
from zetaris import register

ROOT = Path(__file__).resolve().parents[2]
CITY = {"timezone": "Asia/Kolkata"}


def test_supabase_is_the_default_and_leaves_sql_unchanged():
    assert Settings(_env_file=None).zetaris_data == "supabase"
    for q in NAMED_QUERIES.values():
        assert localise(q.lightning, "supabase") == q.lightning
        assert localise(q.lightning, None) == q.lightning


def test_files_mode_rewrites_every_named_query_off_sb_and_the_live_container():
    for q in NAMED_QUERIES.values():
        sql = localise(q.lightning, "files")
        assert not re.search(r"\bsb\.", sql), q.name
        assert not re.search(r"\bnexus\.", sql), q.name
    sql = localise("SELECT * FROM sb.crimes c JOIN nexus.v_crime_unified u ON 1=1 JOIN nexus_feeds.rest_news n", "files")
    assert sql == "SELECT * FROM nexus_fs.crimes c JOIN nexusfs.v_crime_unified u ON 1=1 JOIN nexus_feeds.rest_news n"


def test_every_sb_object_a_query_reads_has_a_file_table():
    read = {t for q in NAMED_QUERIES.values() for t in re.findall(r"\bsb\.([a-z_]+)", q.lightning)}
    assert read <= set(FILE_TABLES)


def test_unknown_data_source_fails_loudly():
    with pytest.raises(ValueError):
        sources("s3")


def test_register_fills_src_placeholders_from_the_same_map():
    stmt = "CREATE OR REPLACE SCHEMASTORE VIEW v WITH CONTAINER {{src:nexus}} AS SELECT * FROM {{src:sb}}.crimes"
    for data, m in SOURCES.items():
        real, shown, _ = register.fill(stmt, CITY, "2026-01-01", "2026-02-01", data)
        assert real == shown == f"CREATE OR REPLACE SCHEMASTORE VIEW v WITH CONTAINER {m['nexus']} AS SELECT * FROM {m['sb']}.crimes"


def test_views_file_renders_to_the_hosted_sql_for_supabase():
    text = (ROOT / "zetaris" / "10_views.sql").read_text(encoding="utf-8")
    hosted = [register.fill(s, CITY, "x", "y", "supabase")[0] for s in register.statements(text)]
    assert hosted[0] == "CREATE SCHEMASTORE CONTAINER nexus"
    assert "WITH CONTAINER nexus AS" in hosted[1] and "FROM sb.crimes" in hosted[1] and "{{src" not in hosted[1]
    files = [register.fill(s, CITY, "x", "y", "files")[0] for s in register.statements(text)]
    assert files[0] == "CREATE SCHEMASTORE CONTAINER nexusfs"
    assert not re.search(r"\bsb\.", files[1]) and "WITH CONTAINER nexusfs AS" in files[1]


def test_register_skips_files_tied_to_the_other_source():
    assert register.FILE_MODES["00_sources.sql"] == {"supabase"}
    assert register.FILE_MODES["30_case.sql"] == {"supabase"}


def test_client_in_files_mode_sends_the_localised_sql(tmp_path):
    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content)["sql"])
        return httpx.Response(200, json={"data": []})

    s = Settings(_env_file=None, zetaris_api_key="k", zetaris_data="files")
    c = ZetarisClient(s, transport=httpx.MockTransport(handler))
    c.named("q_candidates", agent="test", crime_id="CHN-AD-2026-001182", days=45, ring=6)
    assert "nexus_fs.crimes" in sent[0] and not re.search(r"\bsb\.", sent[0])


def test_files_suffix_gives_a_second_copy_its_own_names(monkeypatch):
    from app.adapters.zetaris_sources import SUFFIX_ENV

    monkeypatch.delenv(SUFFIX_ENV, raising=False)
    assert sources("files") == {"sb": "nexus_fs", "nexus": "nexusfs", "fsdir": "fs"}
    monkeypatch.setenv(SUFFIX_ENV, "2")
    assert sources("files") == {"sb": "nexus_fs2", "nexus": "nexusfs2", "fsdir": "fs2"}
    assert sources("supabase")["sb"] == "sb"  # the hosted path never takes a suffix
    assert localise("SELECT * FROM sb.crimes JOIN nexus.dq_flags", "files") == \
        "SELECT * FROM nexus_fs2.crimes JOIN nexusfs2.dq_flags"
    real, _, _ = register.fill('path "file:///x/nexus/{{src:fsdir}}/crimes/" FROM {{src:sb}}', CITY, "a", "b", "files")
    assert real == 'path "file:///x/nexus/fs2/crimes/" FROM nexus_fs2'
    monkeypatch.setenv(SUFFIX_ENV, "Bad;Name")
    with pytest.raises(ValueError):
        sources("files")


def test_staging_folder_follows_the_suffix(monkeypatch):
    import importlib

    from zetaris import stage_files

    monkeypatch.setenv("ZETARIS_FILES_SUFFIX", "2")
    importlib.reload(stage_files)
    assert stage_files.FS_LAYOUT[0] == ("fs/crimes/part-0.parquet", "fs2/crimes")
    monkeypatch.delenv("ZETARIS_FILES_SUFFIX")
    importlib.reload(stage_files)
    assert stage_files.FS_LAYOUT[0] == ("fs/crimes/part-0.parquet", "fs/crimes")
