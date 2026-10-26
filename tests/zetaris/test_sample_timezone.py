"""Sample mode gives the same answer on every machine: the DuckDB session runs in the city's time zone.

Judge path (WS5-12): the examples were recorded on an IST laptop and replayed in a UTC container. DuckDB's
session TimeZone defaulted to the host's, so the sample twins' date logic shifted by 5.5 h and the ANPR
vehicle factor of the hero series fell from 0.85 to 0.5 in the container.
"""

from __future__ import annotations

import duckdb

from app.adapters.zetaris import ZetarisClient
from app.config import Settings, load_city
from app.tracing import Tracer


def test_sample_session_uses_the_city_time_zone_whatever_the_host_zone(tmp_path, monkeypatch):
    orig = duckdb.connect

    def utc_host(*a, **k):  # a container whose host zone is UTC
        con = orig(*a, **k)
        con.execute("SET TimeZone='UTC'")
        return con

    monkeypatch.setattr(duckdb, "connect", utc_host)
    s = Settings(_env_file=None, sample_mode=True, zetaris_api_key="")
    c = ZetarisClient(s, Tracer("t", tmp_path, echo=False))
    assert c._run_sample("SELECT current_setting('TimeZone')") == [[load_city(s.city)["timezone"]]]
