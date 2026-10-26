"""Live q_dq_flags reads the DQ flags snapshot (0007_14); app.dq_status writes it. Sample mode is unchanged."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from app.adapters import dq_rules
from app.adapters.zetaris import NAMED_QUERIES, QueryResult, ZetarisClient, ZetarisError
from app.adapters.zetaris_queries_n2 import DQ_IDS_MAX, DQ_IDS_PER_CALL, dq_flags_params, slot_params
from app.config import Settings
from app.dq_status import SNAPSHOT_LIMIT, build_snapshot, run, run_snapshot
from app.tracing import Tracer

ROOT = Path(__file__).resolve().parents[2]
Q = NAMED_QUERIES["q_dq_flags"]


# =====================
# The query
# =====================

def test_live_sql_reads_the_snapshot_with_a_literal_in_list_and_a_total_order():
    assert "FROM sb.dq_flags_snapshot" in Q.lightning and "nexus.dq_flags" not in Q.lightning
    assert re.search(r"WHERE crime_id IN \(:id01, :id02, .*:id50\)", Q.lightning)  # pushes down to Postgres
    assert "array_contains" not in Q.lightning and "split(" not in Q.lightning
    assert "NULLIF(other_id, '') AS other_id" in Q.lightning  # '' in the table, NULL out, as before
    assert Q.lightning.rstrip().endswith("ORDER BY crime_id, rule, other_id")  # D-031, other_id is in the key
    assert Q.as_of_column and Q.timeout_s and Q.timeout_s <= 10
    assert Q.columns == dq_rules.COLUMNS


def test_sample_twin_and_files_mode_are_unchanged():
    # The twin still filters the rule text by the comma-joined ids (judge-offline must stay identical).
    assert "list_contains(string_split(:ids, ','), crime_id)" in Q.sample
    assert "dq_flags_snapshot" not in Q.sample
    assert Q.lightning_files == ("SELECT crime_id, rule, other_id, detail FROM nexus.dq_flags "
                                 "WHERE array_contains(split(:ids, ','), crime_id) ORDER BY crime_id, rule")


def test_ids_become_fixed_slots_chunked_and_padded():
    one = dq_flags_params({"ids": "A, B,A,,C"})
    assert len(one) == 1 and [one[0][f"id0{i}"] for i in (1, 2, 3, 4)] == ["A", "B", "C", ""]
    assert one[0]["ids"] == "A, B,A,,C"  # kept for the files-mode SQL
    many = dq_flags_params({"ids": ",".join(f"X{i}" for i in range(DQ_IDS_PER_CALL + 1))})
    assert len(many) == 2 and many[1]["id01"] == f"X{DQ_IDS_PER_CALL}" and many[1]["id02"] == ""
    empty = dq_flags_params({"ids": ""})
    assert len(empty) == 1 and set(v for k, v in empty[0].items() if k.startswith("id")) == {""}
    with pytest.raises(ZetarisError):
        dq_flags_params({"ids": ",".join(f"X{i}" for i in range(DQ_IDS_MAX + 1))})


def test_q_cases_still_uses_the_same_slot_helper():
    from app.adapters.zetaris_queries_n2 import CASES_MAX, cases_params

    assert cases_params(["a", "b", "a"]) == slot_params(["a", "b"], CASES_MAX)


# =====================
# The client hooks (live only)
# =====================

def _client(handler, **kw) -> tuple[ZetarisClient, list[str]]:
    sent: list[str] = []

    def wrap(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content)["sql"])
        return handler(sent[-1])

    s = Settings(_env_file=None, zetaris_api_key="k", **kw)
    return ZetarisClient(s, transport=httpx.MockTransport(wrap)), sent


def test_live_call_strips_the_freshness_column_into_the_trace(tmp_path):
    rows = [["C2", "duplicate_fir", "C1", "same theft…", "2026-10-27 01:10:00"],
            ["C2", "bad_geo", None, "no coordinates", "2026-10-27 01:10:00"]]
    c, sent = _client(lambda sql: httpx.Response(200, json={"data": rows}))
    c.tracer = Tracer("t", tmp_path, echo=False)
    r = c.named("q_dq_flags", agent="Planner", ids="C2,C9")
    assert r.source == "zetaris" and r.rows == [row[:4] for row in rows]
    assert "IN ('C2', 'C9', '', " in sent[0] and "dq_flags_snapshot" in sent[0]
    trace = (tmp_path / "trace-t.jsonl").read_text(encoding="utf-8")
    assert "as_of=2026-10-27 01:10:00" in trace


def test_more_than_fifty_ids_run_as_several_calls_merged_in_order():
    def answer(sql: str) -> httpx.Response:
        first = re.search(r"IN \('([^']+)'", sql).group(1)
        return httpx.Response(200, json={"data": [[first, "bad_geo", None, "x", "2026-10-27 01:00:00"]]})

    c, sent = _client(answer)
    ids = [f"C{i:03d}" for i in range(120, 0, -1)]
    r = c.named("q_dq_flags", agent="Planner", ids=",".join(ids))
    assert len(sent) == 3 and [row[0] for row in r.rows] == sorted(row[0] for row in r.rows)


def test_files_mode_keeps_the_rule_views_with_its_suffix(monkeypatch):
    monkeypatch.setenv("ZETARIS_FILES_SUFFIX", "2")
    c, sent = _client(lambda sql: httpx.Response(200, json={"data": [["C1", "bad_geo", None, "x"]]}), zetaris_data="files")
    r = c.named("q_dq_flags", agent="Planner", ids="C1")
    assert "FROM nexusfs2.dq_flags" in sent[0] and "dq_flags_snapshot" not in sent[0]
    assert r.rows == [["C1", "bad_geo", None, "x"]]  # four columns: nothing stripped


def test_sample_mode_never_runs_the_hooks(tmp_path):
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    c = ZetarisClient(s, tracer=Tracer("t", tmp_path, echo=False))
    r = c.named("q_dq_flags", agent="Planner", ids="," * 400 + "X")  # would not even pass expand's cap if it ran
    assert r.source == "sample"


# =====================
# The writer
# =====================

class FakeZ:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def named(self, name, *, agent, **_):
        if self.exc:
            raise self.exc
        if name == "q_dq_flags_all":
            return self.result
        return QueryResult(name=name, query_id="dq-1", ms=1, source="zetaris",
                           rows=[[r, 1] for r, _ in __import__("app.adapters.zetaris_queries_n1", fromlist=["x"]).DQ_RULE_VIEWS])


class FakeSb:
    def __init__(self):
        self.rpcs, self.upserts = [], []

    def rpc(self, fn, args):
        self.rpcs.append((fn, args))
        return len(args["p_rows"])

    def select(self, table, params=None):
        return []

    def upsert(self, table, rows, on_conflict):
        self.upserts.append(rows)
        return rows


def _all(source="zetaris", n=None):
    rows = [["C1", "duplicate_fir", "C2", "same theft"], ["C1", "unmapped_section", None, "legacy sections"]]
    if n:
        rows = [["C1", "bad_geo", None, "x"]] * n
    return QueryResult(name="q_dq_flags_all", query_id="all-1", ms=60000, source=source, rows=rows)


def test_live_pass_becomes_snapshot_rows_with_severity():
    rows, why, qid = build_snapshot(FakeZ(_all()))
    assert why == "ok" and qid == "all-1"
    assert rows == [
        {"crime_id": "C1", "rule": "duplicate_fir", "other_id": "C2", "severity": "warn", "detail": "same theft"},
        {"crime_id": "C1", "rule": "unmapped_section", "other_id": "", "severity": "info", "detail": "legacy sections"},
    ]


@pytest.mark.parametrize("z", [FakeZ(_all("sample")), FakeZ(_all(n=SNAPSHOT_LIMIT)), FakeZ(exc=RuntimeError("down"))])
def test_sample_truncated_or_failed_passes_write_nothing(z, tmp_path):
    sb = FakeSb()
    out = run_snapshot(sb, z, Tracer("t", tmp_path, echo=False))
    assert sb.rpcs == [] and "snapshot_error" in out


def test_run_records_the_snapshot_on_the_dq_row(tmp_path):
    sb = FakeSb()
    row = run(None, sb, FakeZ(_all()), Tracer("t", tmp_path, echo=False))
    assert sb.rpcs[0][0] == "replace_dq_flags_snapshot" and len(sb.rpcs[0][1]["p_rows"]) == 2
    assert row["detail"]["snapshot_rows"] == 2 and row["detail"]["snapshot_at"] == sb.rpcs[0][1]["p_computed_at"]


# =====================
# The migration and the registration
# =====================

def test_migration_locks_the_table_down():
    sql = (ROOT / "supabase" / "migrations" / "0007_14_dq_flags_snapshot.sql").read_text(encoding="utf-8").lower()
    assert "enable row level security" in sql
    assert "revoke all on public.dq_flags_snapshot from public, anon, authenticated" in sql
    assert "grant select on public.dq_flags_snapshot to zetaris_reader" in sql
    assert "for select to zetaris_reader using (true)" in sql  # no BYPASSRLS: without it Zetaris reads 0 rows
    assert "primary key (crime_id, rule, other_id)" in sql
    assert "security definer set search_path = public, pg_temp" in sql
    assert "revoke execute on function public.replace_dq_flags_snapshot(jsonb, timestamptz) from public, anon, authenticated" in sql
    assert "grant execute on function public.replace_dq_flags_snapshot(jsonb, timestamptz) to service_role" in sql
    assert "-- rollback:" in sql
    assert not re.search(r"grant (insert|update|delete|all)[^;]*zetaris_reader", sql)


def test_registration_is_its_own_statement():
    text = (ROOT / "zetaris" / "00_sources.sql").read_text(encoding="utf-8")
    assert 'REGISTER DATASOURCE TABLES ("dq_flags_snapshot") FROM sb;' in text
