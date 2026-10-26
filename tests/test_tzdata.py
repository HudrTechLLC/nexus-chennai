"""Windows judges: Python on Windows ships no IANA time-zone database, so `zoneinfo` needs the
`tzdata` package. Without it, importing app.main fails with ZoneInfoNotFoundError('Asia/Kolkata')
(found by the fresh-clone venv run). On Linux the system zoneinfo hides the gap, so this test
also checks that the requirement stays declared."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REQ = Path(__file__).resolve().parents[1] / "services" / "api" / "requirements.txt"


def test_city_time_zone_resolves() -> None:
    assert datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Kolkata")).utcoffset() == timedelta(hours=5, minutes=30)


def test_tzdata_is_a_runtime_requirement() -> None:
    names = {line.split("==")[0].strip().lower() for line in REQ.read_text(encoding="utf-8").splitlines() if line.strip()}
    assert "tzdata" in names
