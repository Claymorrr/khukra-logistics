"""Tests for disruption ingest, discovery, and forecast."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from khukra_logistics.disruption.cache import load_panel, save_signal
from khukra_logistics.disruption.service import DisruptionIntelligenceService
from khukra_logistics.disruption.statistics import (
    composite_risk_index,
    discover_insights,
    forecast_composite,
    profile_panel,
)


def _synthetic_signal(n: int, seed: int, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=date.today(), periods=n, freq="B")
    values = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    return pd.DataFrame({"date": dates, "value": values})


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_LOGISTICS_DATA_ROOT", str(tmp_path))
    return DisruptionIntelligenceService()


def test_load_panel_merges_tz_aware_and_naive_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_LOGISTICS_DATA_ROOT", str(tmp_path))
    save_signal(
        "vix",
        pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "value": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        ),
    )
    save_signal(
        "news_stress",
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-02", "2024-01-04"], utc=True),
                "value": [2.0, 3.0],
            }
        ),
    )
    panel = load_panel(["vix", "news_stress"])
    assert not panel.empty
    assert "vix" in panel.columns and "news_stress" in panel.columns
    assert panel["date"].dt.tz is None


def test_catalog_lists_signals(service):
    catalog = service.catalog()
    assert catalog["signal_count"] >= 9
    assert "financial_stress" in catalog["categories"]


def test_discover_and_forecast_on_synthetic_panel(service, tmp_path):
    for i, sid in enumerate(["vix", "oil_wti", "hy_oas"]):
        save_signal(sid, _synthetic_signal(200, seed=i, drift=0.02 * i))

    panel = load_panel()
    assert not panel.empty
    profile = profile_panel(panel)
    assert profile["total"] == 3

    discovery = discover_insights(panel)
    assert discovery["insight_count"] >= 0
    assert discovery["methodology"]

    composite = composite_risk_index(panel)
    assert "current" in composite
    assert composite["series"]["composite_z"]

    forecast = forecast_composite(panel, horizon=14)
    assert len(forecast["forecast"]) == 14


def test_service_discover_requires_cache(service):
    with pytest.raises(ValueError, match="No cached"):
        service.discover()


def test_discover_api_json_serializable(service, monkeypatch):
    def fake_fred(series_id, start=None, end=None):
        return _synthetic_signal(200, seed=1)

    monkeypatch.setattr("khukra_logistics.disruption.service.fred.fetch_daily_series", fake_fred)
    monkeypatch.setattr("khukra_logistics.disruption.service.yahoo.fetch_daily_series", fake_fred)
    service.refresh(["vix", "oil_wti"], years=2)
    import json

    result = service.discover()
    json.dumps(result)  # must not raise
    assert result["discovery"]["insight_count"] >= 0


def test_panel_data_returns_series(service, tmp_path):
    for i, sid in enumerate(["vix", "oil_wti"]):
        save_signal(sid, _synthetic_signal(200, seed=i))

    panel = service.panel_data(tail_days=100, scale="rebased", table_rows=20)
    import json

    json.dumps(panel)
    assert panel["row_count"] == 100
    assert len(panel["series"]) == 100
    assert len(panel["recent_rows"]) == 20
    assert panel["profile"]["total"] == 2
    assert "vix" in panel["signal_ids"]


def test_explore_falls_back_to_full_panel_when_only_news_selected(service, tmp_path, monkeypatch):
    monkeypatch.setenv("KHUKRA_LOGISTICS_DATA_ROOT", str(tmp_path))
    for i, sid in enumerate(["vix", "oil_wti", "hy_oas"]):
        save_signal(sid, _synthetic_signal(200, seed=i))
    save_signal(
        "news_stress",
        pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
                "value": [1.0, 2.0],
            }
        ),
    )
    result = service.explore(["news_stress"])
    assert result["signal_scope"] == "all_cached"
    assert len(result["methods_run"]) >= 5


def test_refresh_with_mocked_adapters(service, monkeypatch):
    def fake_fred(series_id, start=None, end=None):
        return _synthetic_signal(100, seed=1)

    def fake_yahoo(ticker, start=None, end=None):
        return _synthetic_signal(100, seed=2)

    monkeypatch.setattr(
        "khukra_logistics.disruption.service.fred.fetch_daily_series",
        fake_fred,
    )
    monkeypatch.setattr(
        "khukra_logistics.disruption.service.yahoo.fetch_daily_series",
        fake_yahoo,
    )
    def fake_basket(start=None, end=None):
        return _synthetic_signal(100, seed=3)

    monkeypatch.setattr(
        "khukra_logistics.disruption.service.yahoo.fetch_shipping_basket",
        fake_basket,
    )
    result = service.refresh(["vix", "shipping_basket"], years=2)
    assert result["signals_refreshed"] == 2
    status = service.status()
    assert status["covered_count"] == 2

    discovery = service.discover()
    assert discovery["discovery"]["insight_count"] >= 0
    assert discovery["composite_risk"]["current"] is not None
