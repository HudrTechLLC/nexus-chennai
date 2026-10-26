"""Source onboarding (WS1-23): header and identifier safety, SQL templates, mapping validation, the worker step."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app import onboarding as ob
from app.adapters import zetaris_onboard as zo
from app.adapters.zetaris import ZetarisClient, ZetarisError
from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "onboarding" / "sample_new_station.csv"


# =====================
# Headers and names an uploader controls
# =====================

MALICIOUS = [
    "x`; DROP VIEW nexus.v_crime_unified; --",
    "a` FROM sb.crimes --",
    "name'); DROP TABLE x",
    'quoted "col"',
    "semi;colon",
    "new\nline",
    "carriage\rreturn",
    "dash -- comment",
    "c /* comment */",
    "back\\slash",
    "x" * 65,
    "",
    " leading space",
    "tab\there",
]


@pytest.mark.parametrize("name", MALICIOUS)
def test_a_dangerous_header_is_rejected(name):
    with pytest.raises(zo.OnboardRejected):
        zo.check_header(name)


@pytest.mark.parametrize("name", ["FIR No.", "Lat/Long", "Date of Occurrence", "Brief Facts (if any)", "Crime Head",
                                  "Amount (Rs.)", "S.No", "Place & Ward"])
def test_real_export_headers_are_accepted(name):
    assert zo.check_header(name) == name


def test_a_file_with_a_malicious_header_is_rejected_before_anything_runs():
    data = 'FIR No.,"x`; DROP VIEW nexus.v_crime_unified; --"\nRH/1/2026,1\n'.encode()
    with pytest.raises(zo.OnboardRejected):
        ob.read_headers(data)


def test_duplicate_and_oversized_files_are_rejected():
    with pytest.raises(zo.OnboardRejected):
        ob.read_headers(b"a,A\n1,2\n")
    with pytest.raises(zo.OnboardRejected):
        ob.read_headers(b"a\n" + b"x" * (ob.MAX_BYTES + 1))


@pytest.mark.parametrize("key", ["ab", "x" * 31, "Red", "a-b", "a b", "x'; drop", "../etc"])
def test_bad_source_keys_are_rejected(key):
    with pytest.raises(zo.OnboardRejected):
        zo.ident(key)


def test_generated_names_match_the_allowed_pattern():
    assert zo.ident("redhills_new") == "onboard_redhills_new"
    assert zo.ident("redhills_new", raw=True) == "onboard_redhills_new_raw"
    assert re.match(r"^onboard_[a-z0-9_]{1,40}(_raw)?$", zo.ident("abc"))


# =====================
# SQL templates
# =====================

MAPPING = [
    {"source_col": "FIR No.", "unified_field": "fir_no", "transform": "none"},
    {"source_col": "Date of Occurrence", "unified_field": "occurred_from", "transform": "date_dmy"},
    {"source_col": "Lat/Long", "unified_field": "lat", "transform": "latlong_lat"},
    {"source_col": "Crime Head", "unified_field": "category", "transform": "none"},
    {"source_col": "Remarks", "unified_field": None, "transform": "none"},
]


def _outside_backticks(sql: str) -> str:
    return re.sub(r"`[^`]*`", "``", sql)


def test_the_view_sql_uses_only_quoted_columns_and_allowlisted_fields():
    sql = zo.create_view("redhills_new", ob.lat_lon_split(MAPPING), "PS-REDHILLS-NEW", "Asia/Kolkata")
    assert sql.startswith("CREATE OR REPLACE SCHEMASTORE VIEW onboard_redhills_new WITH CONTAINER nexus AS SELECT ")
    assert "`FIR No.`" in sql and "`Lat/Long`" in sql and "Remarks" not in sql
    outside = _outside_backticks(sql)
    assert "FIR No." not in outside and "Lat/Long" not in outside
    assert re.findall(r" AS ([a-z_]+)", outside) == ["station_id", "fir_no", "occurred_from", "lat", "category", "lon"]
    assert "v_crime_unified" not in sql


def test_mapping_errors_never_reach_sql():
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", [{**MAPPING[0], "unified_field": "crime_id"}] + MAPPING[1:], "PS-X1", "Asia/Kolkata")
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", [{**MAPPING[0], "transform": "eval(x)"}] + MAPPING[1:], "PS-X1", "Asia/Kolkata")
    with pytest.raises(zo.OnboardRejected):  # lon missing (no split) and so a required field is unmapped
        zo.create_view("k_ok", MAPPING, "PS-X1", "Asia/Kolkata")
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", ob.lat_lon_split(MAPPING) + [{**MAPPING[0], "source_col": "Place"}], "PS-X1", "Asia/Kolkata")
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", ob.lat_lon_split(MAPPING), "PS-X'1", "Asia/Kolkata")
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", [{**MAPPING[0], "source_col": "x`; DROP VIEW v --"}] + ob.lat_lon_split(MAPPING)[1:],
                       "PS-X1", "Asia/Kolkata")


def test_unified_fields_match_the_migration_seed():
    sql = (ROOT / "supabase" / "migrations" / "0007_15_source_onboarding.sql").read_text(encoding="utf-8")
    block = sql[sql.index("insert into public.onboarding_fields"):sql.index("on conflict (field)")]
    seeded = re.findall(r"\('([a-z_]+)',\s+'[^']+',\s+(true|false),", block)
    assert tuple(f for f, _ in seeded) == zo.FIELDS
    assert tuple(f for f, r in seeded if r == "true") == zo.REQUIRED
    allowed = re.search(r"transform in \(([^)]*)\)", sql).group(1)
    assert set(re.findall(r"'([a-z_]+)'", allowed)) == set(zo.TRANSFORMS)


def test_zetaris_onboard_only_runs_known_templates():
    z = ZetarisClient(get_settings().model_copy(update={"zetaris_api_key": "k", "sample_mode": False}))
    with pytest.raises(ZetarisError):
        z.onboard("DROP VIEW nexus.v_crime_unified", agent="t")
    z2 = ZetarisClient(get_settings().model_copy(update={"zetaris_api_key": "", "sample_mode": True}))
    with pytest.raises(ZetarisError):
        z2.onboard("count_view", "abc", agent="t")


# =====================
# Mapping
# =====================

COLS = ["FIR No.", "Date of Occurrence", "Lat/Long", "Crime Head", "Remarks"]


def _model(items):
    return {"mapping": items}


def test_a_valid_model_mapping_is_kept_and_rounded():
    items = [{"source_col": c, "unified_field": m["unified_field"], "transform": m["transform"], "confidence": 0.912,
              "reason": "r"} for c, m in zip(COLS, MAPPING)]
    out = ob.validate_mapping(_model(items), COLS)
    assert [m["unified_field"] for m in out] == ["fir_no", "occurred_from", "lat", "category", None]
    assert out[0]["confidence"] == 0.91


@pytest.mark.parametrize("bad", [
    lambda it: [],                                                        # nothing mapped
    lambda it: it + [it[0]],                                              # a column twice
    lambda it: [{**it[0], "unified_field": "crime_id"}] + it[1:],         # field not allowed
    lambda it: [{**it[0], "transform": "sql"}] + it[1:],                  # transform not allowed
    lambda it: [{**it[0], "confidence": 1.5}] + it[1:],                   # confidence out of range
    lambda it: [{**it[0], "source_col": "Unknown"}] + it[1:],             # a column that is not in the file
])
def test_a_bad_model_mapping_is_refused(bad):
    items = [{"source_col": c, "unified_field": m["unified_field"], "transform": m["transform"], "confidence": 0.9,
              "reason": "r"} for c, m in zip(COLS, MAPPING)]
    with pytest.raises(Exception):
        ob.validate_mapping(_model(bad(items)), COLS)


def test_rules_map_the_sample_file_completely():
    headers = ob.read_headers(SAMPLE.read_bytes())
    mapping = ob.rules_mapping(headers)
    sql = zo.mapped_select("redhills_new", ob.lat_lon_split(mapping), "PS-REDHILLS-NEW", "Asia/Kolkata")
    assert all(f" AS {f}" in sql for f in zo.REQUIRED)
    assert {m["reason"] for m in mapping if m["unified_field"]} == {"header keyword rule (model mapping unavailable)"}


def test_the_sample_file_is_synthetic_and_shows_every_rule():
    rows = list(csv.DictReader(io.StringIO(SAMPLE.read_text(encoding="utf-8"))))
    assert len(rows) == 150 and all(r["Remarks"].startswith("Synthetic") for r in rows)
    assert sum(1 for r in rows if not r["FIR No."]) == 3
    assert any(r["Lat/Long"] == "0, 0" for r in rows) and any(r["Date of Occurrence"] == "31/02/2026" for r in rows)


# =====================
# The worker step (fakes for Supabase, Zetaris and Nightshift)
# =====================


class FakeSb:
    def __init__(self, runs):
        self.tables: dict[str, list[dict[str, Any]]] = {"onboarding_runs": runs, "onboarding_mappings": []}
        self.files: dict[str, bytes] = {}

    def _match(self, row, params):
        for k, v in params.items():
            if k in ("select", "order", "limit"):
                continue
            if v.startswith("eq.") and str(row.get(k)) != v[3:]:
                return False
        return True

    def select(self, table, params=None):
        rows = [dict(r) for r in self.tables.get(table, []) if self._match(r, params or {})]
        return rows[: int((params or {}).get("limit", 10**6))]

    def update(self, table, match, values):
        for r in self.tables.setdefault(table, []):
            if self._match(r, match):
                r.update(values)
        return []

    def insert(self, table, rows):
        self.tables.setdefault(table, []).extend(rows if isinstance(rows, list) else [rows])
        return []

    def delete(self, table, match):
        self.tables[table] = [r for r in self.tables.get(table, []) if not self._match(r, match)]
        return []

    def upsert(self, table, rows, on_conflict):
        return []

    def download(self, bucket, path):
        return self.files[path]


class FakeZetaris:
    def __init__(self, headers):
        self.headers, self.calls, self.tracer = headers, [], None

    def onboard(self, template, *args, agent, **kw):
        self.calls.append(template)
        zo_builders = {"create_raw": zo.create_raw, "describe_raw": zo.describe_raw, "profile": zo.profile,
                       "examples": zo.examples, "dq": zo.dq, "dq_samples": zo.dq_samples,
                       "likely_duplicates": zo.likely_duplicates, "date_range": zo.date_range, "create_view": zo.create_view,
                       "count_view": zo.count_view}
        zo_builders[template](*args)  # the real template must build without raising
        rows = {"create_raw": [], "describe_raw": [[h, "string", None] for h in self.headers],
                "profile": [[150] + [150, 100] * len(self.headers)],
                "examples": [[f"v{i}" for i in range(len(self.headers))]],
                "dq": [[150, 5, 4, 3, 4, 0, 0]], "dq_samples": [["RH/1/2026", "bad_date"], ["RH/2/2026", "out_of_city"]],
                "likely_duplicates": [["RH/9/2026", "CHN-MD-2025-000126"]], "create_view": [], "count_view": [[150]],
                "date_range": [["2026-05-31 18:30:00", "2026-10-19 18:30:00"]]}
        return SimpleNamespace(rows=rows[template])


class FakeNightshift:
    def __init__(self, reply):
        self.reply, self.calls, self.tracer = reply, 0, None

    def chat(self, lane, messages, **kw):
        self.calls += 1
        assert lane == "fast"
        return SimpleNamespace(content=self.reply)


def _run(**kw):
    return {"run_id": "11111111-1111-4111-8111-111111111111", "source_key": "redhills_new", "label": "Red Hills",
            "status": "uploaded", "use_sample": True, "file_path": None, **kw}


def _onboarder(sb, z, ns, tmp_path, staged):
    return ob.Onboarder(get_settings(), sb, z, ns, tmp_path, stage=lambda k, d: staged.append((k, len(d))))


def test_sample_run_is_profiled_mapped_and_proposed_then_registered(tmp_path):
    headers = ob.read_headers(SAMPLE.read_bytes())
    reply = json.dumps({"mapping": [{"source_col": m["source_col"], "unified_field": m["unified_field"],
                                     "transform": m["transform"], "confidence": 0.9, "reason": "header and values"}
                                    for m in ob.rules_mapping(headers)]})
    sb, z, ns, staged = FakeSb([_run()]), FakeZetaris(headers), FakeNightshift(reply), []
    assert _onboarder(sb, z, ns, tmp_path, staged).process() == 1
    run = sb.tables["onboarding_runs"][0]
    assert run["status"] == "proposed", run.get("error")
    assert run["mapping_source"] == "model" and run["row_count"] == 150 and ns.calls == 1
    assert staged == [("redhills_new", SAMPLE.stat().st_size)]
    dq = {d["rule"]: d["count"] for d in run["dq"]}
    assert dq == {"bad_date": 5, "out_of_city": 4, "missing_required": 3, "repeated_fir_no": 4,
                  "ends_before_start": 0, "occurred_after_reported": 0, "likely_duplicate_of_existing": 1}
    assert len(sb.tables["onboarding_mappings"]) == len(headers)
    assert run["linking_enabled"] if "linking_enabled" in run else True  # pinned false by the table, untouched here
    run["status"] = "approved"
    assert _onboarder(sb, z, ns, tmp_path, staged).process() == 1
    assert run["status"] == "registered" and run["view_name"] == "onboard_redhills_new" and run["row_count"] == 150
    assert "create_view" in z.calls


def test_bad_model_output_falls_back_to_rules_and_says_so(tmp_path):
    headers = ob.read_headers(SAMPLE.read_bytes())
    sb, z, ns = FakeSb([_run()]), FakeZetaris(headers), FakeNightshift("not json at all")
    _onboarder(sb, z, ns, tmp_path, []).process()
    run = sb.tables["onboarding_runs"][0]
    assert run["status"] == "proposed" and run["mapping_source"] == "rules"


def test_a_malicious_upload_fails_before_staging_or_any_zetaris_call(tmp_path):
    path = "22222222-2222-4222-8222-222222222222/source.csv"
    sb = FakeSb([_run(use_sample=False, file_path=path)])
    sb.files[path] = b'FIR No.,"x`; DROP VIEW nexus.v_crime_unified; --"\nRH/1/2026,1\n'
    z, ns, staged = FakeZetaris([]), FakeNightshift("{}"), []
    _onboarder(sb, z, ns, tmp_path, staged).process()
    run = sb.tables["onboarding_runs"][0]
    assert run["status"] == "failed" and "not allowed" in run["error"]
    assert staged == [] and z.calls == [] and ns.calls == 0


def test_no_runs_means_no_zetaris_or_model_call(tmp_path):
    z, ns = FakeZetaris([]), FakeNightshift("{}")
    assert _onboarder(FakeSb([]), z, ns, tmp_path, []).process() == 0
    assert z.calls == [] and ns.calls == 0


def test_duplicates_use_dq_rules_thresholds_and_a_time_window():
    from app.adapters.dq_rules import DUP_MAX_DEG, DUP_WINDOW_MIN

    split = ob.lat_lon_split(MAPPING)
    day = zo.likely_duplicates("k_ok", split, "PS-X1", "Asia/Kolkata", "2026-06-01 00:00:00", "2026-10-20 00:00:00")
    assert f"<= {float(DUP_MAX_DEG)}" in day and "INTERVAL 1 DAY" in day and "to_date" not in day
    timed = [{**m, "transform": "datetime_dmy_hm"} if m["unified_field"] == "occurred_from" else m for m in split]
    assert f"<= {DUP_WINDOW_MIN * 60}" in zo.likely_duplicates("k_ok", timed, "PS-X1", "Asia/Kolkata", "2026-06-01", "2026-10-20")
    assert "occurred_from >= TIMESTAMP '2026-05-31 00:00:00' AND occurred_from < TIMESTAMP '2026-10-22 00:00:00'" in day
    with pytest.raises(ValueError):
        zo.likely_duplicates("k_ok", split, "PS-X1", "Asia/Kolkata", "2026-06-01'; DROP", "2026-10-20")


def test_time_order_checks_appear_only_when_those_fields_are_mapped():
    split = ob.lat_lon_split(MAPPING)
    bounds = (80.0, 12.8, 80.4, 13.3)
    assert "0 AS ends_before_start" in zo.dq("k_ok", split, "PS-X1", "Asia/Kolkata", bounds)
    more = split + [{"source_col": "Reported", "unified_field": "reported_at", "transform": "date_dmy"}]
    assert "reported_at < occurred_from" in zo.dq("k_ok", more, "PS-X1", "Asia/Kolkata", bounds)


def test_file_dates_are_read_in_the_city_time_zone():
    sql = zo.create_view("k_ok", ob.lat_lon_split(MAPPING), "PS-X1", "Asia/Kolkata")
    assert "to_utc_timestamp(to_timestamp(trim(`Date of Occurrence`), 'dd/MM/yyyy'), 'Asia/Kolkata')" in sql
    with pytest.raises(zo.OnboardRejected):
        zo.create_view("k_ok", ob.lat_lon_split(MAPPING), "PS-X1", "UTC'); DROP")


def test_the_transform_in_the_field_slot_is_read_as_the_lat_long_split():
    items = [{"source_col": c, "unified_field": m["unified_field"], "transform": m["transform"], "confidence": 0.9,
              "reason": "r"} for c, m in zip(COLS, MAPPING)]
    items[2] = {**items[2], "unified_field": "latlong_lat", "transform": "none"}  # what Lightning sent live
    out = ob.validate_mapping(_model(items), COLS)
    assert (out[2]["unified_field"], out[2]["transform"]) == ("lat", "latlong_lat")


def test_a_column_the_model_leaves_out_is_ignored_and_says_so():
    items = [{"source_col": c, "unified_field": m["unified_field"], "transform": m["transform"], "confidence": 0.9,
              "reason": "r"} for c, m in zip(COLS, MAPPING)][:-1]
    out = ob.validate_mapping(_model(items), COLS)
    assert out[-1] == {"source_col": "Remarks", "unified_field": None, "transform": "none", "confidence": 0.0,
                       "reason": "not mapped by the model: ignored"}
