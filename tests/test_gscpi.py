"""Tests for NY Fed GSCPI adapter."""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd

from khukra_logistics.disruption.adapters import gscpi


def test_fetch_monthly_series_parses_latest_vintage(monkeypatch):
    csv = """Date,Jan-2020,Feb-2026
01-Jan-2020,0.5,0.6
01-Feb-2020,0.7,0.8
"""
    class FakeResp:
        def read(self):
            return csv.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(gscpi, "urlopen", lambda req, timeout=30: FakeResp())
    df = gscpi.fetch_monthly_series()
    assert len(df) == 2
    assert df["value"].tolist() == [0.6, 0.8]


def test_expand_to_business_days_forward_fills():
    monthly = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "value": [1.0, 2.0],
        }
    )
    daily = gscpi.expand_to_business_days(monthly)
    assert len(daily) > len(monthly)
    assert daily["value"].iloc[-1] == 2.0
    assert daily["date"].min().date() == date(2024, 1, 1)
