"""q_cases: q_case for up to 25 crimes in one Zetaris trip (sb.case_bundle_v, IN pushed down)."""

import json

import pytest

from app.adapters.zetaris import NAMED_QUERIES, render
from app.adapters.zetaris_queries_n1 import CASE_COLUMNS as N1_CASE_COLUMNS
from app.adapters.zetaris_queries_n2 import CASE_COLUMNS, CASES_MAX, cases_params

from .test_twins import sample  # noqa: F401  (parquet fixture with CHN-A-1 and CHN-A-2)


def test_contract_is_q_case():
    assert CASE_COLUMNS == N1_CASE_COLUMNS
    assert NAMED_QUERIES["q_cases"].columns == NAMED_QUERIES["q_case"].columns


def test_params_chunk_dedupe_and_pad():
    ids = [f"C{i}" for i in range(30)] + ["C1", "", None]
    chunks = cases_params(ids)
    assert len(chunks) == 2 and len(chunks[0]) == CASES_MAX
    assert [v for v in chunks[0].values() if v] == [f"C{i}" for i in range(25)]
    assert [v for v in chunks[1].values() if v] == [f"C{i}" for i in range(25, 30)]
    assert cases_params([]) == []


def test_lightning_is_one_in_list_read_of_the_bundle_view():
    sql = render(NAMED_QUERIES["q_cases"].lightning, cases_params(["A", "B"])[0])
    assert "FROM sb.case_bundle_v WHERE crime_id IN ('A', 'B', ''," in sql and sql.endswith("ORDER BY crime_id")


def test_twin_returns_the_same_rows_as_q_case(sample):  # noqa: F811
    many = sample.named("q_cases", agent="Planner", **cases_params(["CHN-A-2", "CHN-A-1", "NOPE"])[0]).dicts()
    assert [r["crime_id"] for r in many] == ["CHN-A-1", "CHN-A-2"]
    for row in many:
        (one,) = sample.named("q_case", agent="Planner", crime_id=row["crime_id"]).dicts()
        assert row == one
    assert json.loads(many[0]["vehicles"])[0]["plate"] == "TN09??4471"


@pytest.mark.parametrize("n", [1, CASES_MAX])
def test_every_slot_is_bound(n):
    params = cases_params([f"X{i}" for i in range(n)])[0]
    render(NAMED_QUERIES["q_cases"].lightning, params)
    render(NAMED_QUERIES["q_cases"].sample, params)
