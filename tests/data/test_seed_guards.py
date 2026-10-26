"""data/seed.py never retires or overwrites crimes the generator did not make (console FIRs)."""

import uuid

import pytest

from data import seed
from data.generator import cli


class FakeCursor:
    def __init__(self, results):
        self.results = list(results)

    def execute(self, sql, params=None):
        self._rows = self.results.pop(0)

    def fetchall(self):
        return self._rows


def gen_row(cid, st, fir):
    return (cid, st, fir, str(uuid.uuid5(seed.GEN_NS, cid)))


def test_namespace_matches_generator():
    assert seed.GEN_NS == cli.NS


def test_foreign_crimes_are_the_ones_without_the_generator_signature():
    cur = FakeCursor([[gen_row("CHN-AD-2026-000001", "PS-ADYAR-J2", "1/2026"),
                       ("CHN-AD-2026-001231", "PS-ADYAR-J2", "1231/2026", "10da1d10-af2f-4472-a7cd-fb7ffbfefa20")]])
    assert seed._foreign_crimes(cur) == {"CHN-AD-2026-001231": ("PS-ADYAR-J2", "1231/2026")}


def test_guard_refuses_a_generated_crime_on_a_console_fir_number():
    foreign = {"CHN-AD-2026-001231": ("PS-ADYAR-J2", "1231/2026")}
    with pytest.raises(RuntimeError, match="filed outside the generator"):
        seed._guard_foreign(FakeCursor([[("CHN-AD-2026-009999", "PS-ADYAR-J2", "1231/2026")]]), foreign)
    with pytest.raises(RuntimeError):
        seed._guard_foreign(FakeCursor([[("CHN-AD-2026-001231", "PS-ADYAR-J2", "1231/2026")]]), foreign)
    seed._guard_foreign(FakeCursor([[("CHN-AD-2026-000002", "PS-ADYAR-J2", "2/2026")]]), foreign)
