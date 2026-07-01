"""Tests for fast production-model forecast path."""

from __future__ import annotations

import numpy as np
import pandas as pd

from khukra_logistics.disruption.statistics import production_model_forecast


def _synthetic_panel(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    trend = np.linspace(0, 2, n)
    noise = rng.normal(0, 0.3, n)
    return pd.DataFrame(
        {
            "date": dates,
            "vix": 20 + trend * 3 + noise,
            "oil_wti": 70 + trend * 5 + noise,
            "shipping_basket": 15 + trend * 2 + noise,
            "gscpi": 1 + trend * 0.1 + noise,
            "eurusd": 1.1 + noise * 0.01,
        }
    )


def test_production_model_forecast_returns_series():
    panel = _synthetic_panel(200)
    result = production_model_forecast(panel, horizon=14)
    assert result["production_method"] == "mean_reversion"
    assert len(result["production_series"]["dates"]) >= 40
    assert len(result["forecast"]) == 14
    assert result["smooth_days"] >= 1
