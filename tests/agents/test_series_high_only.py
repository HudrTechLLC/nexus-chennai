"""#16: series from HIGH-band or analyst-approved links only, behind SERIES_HIGH_ONLY (off by default)."""

from __future__ import annotations

from app.agents.series import detect_series, strong_link
from app.config import Settings
from app.eval.core import series_purity


def link(a, b, band="medium", status="pending", score=0.6):
    return {"alert_id": f"LA-{a}-{b}", "kind": "pair", "crimes": [a, b], "band": band, "status": status,
            "score": score, "stations": []}


# A 5-case chain: one HIGH link, one analyst-approved MEDIUM link, two pending MEDIUM links, one rejected HIGH.
ALERTS = [link("A", "B", band="high", score=0.8), link("B", "C", status="approved"), link("C", "D"),
          link("D", "E"), link("E", "F", band="high", status="rejected")]


def test_switch_is_off_by_default():
    assert Settings(_env_file=None).series_high_only is False


def test_switch_reads_the_environment(monkeypatch):
    monkeypatch.setenv("SERIES_HIGH_ONLY", "true")
    assert Settings(_env_file=None).series_high_only is True


def test_off_is_the_existing_behaviour():
    off = detect_series(ALERTS)
    assert off == detect_series(ALERTS, high_only=False)
    assert [s["crime_ids"] for s in off] == [["A", "B", "C", "D", "E"]]  # every non-rejected link joins


def test_on_keeps_only_high_or_approved_links():
    on = detect_series(ALERTS, high_only=True)
    assert [s["crime_ids"] for s in on] == [["A", "B", "C"]]
    assert on[0]["alert_ids"] == ["LA-A-B", "LA-B-C"]


def test_on_never_revives_a_rejected_high_link():
    assert detect_series([link("X", "Y", band="high", status="rejected"), link("Y", "Z", band="high")],
                         high_only=True) == []


def test_strong_link():
    assert strong_link({"band": "high"}) and strong_link({"band": "medium", "status": "approved"})
    assert not strong_link({"band": "medium", "status": "pending"}) and not strong_link({})


def test_runner_passes_the_switch_through(monkeypatch):
    from app.graph import runner

    seen = []
    monkeypatch.setattr(runner, "detect_series", lambda alerts, excluded=frozenset(), *, high_only=False:
                        seen.append(high_only) or [])

    class G:
        series_high_only = True

    assert runner._detect_series(G(), ALERTS) == ([], {})
    assert seen == [True]


def test_eval_side_metric_uses_high_band_only():
    series = [{"series_id": "S1", "crime_ids": ["A", "B", "C"]}, {"series_id": "S2", "crime_ids": ["D", "E"]}]
    high = [("A", "B"), ("B", "C")]
    assert series_purity(high, series) == {"predicted_series": 1, "mean_purity": 1.0}
