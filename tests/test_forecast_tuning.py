"""Tests for walk-forward MAE tuning."""

from __future__ import annotations

import numpy as np
import pandas as pd

from khukra.disruption.forecast_tuning import (
    apply_recommended_config,
    build_predictor,
    default_forecast_config,
    optimize_forecast_mae,
    tune_mean_reversion_on_series,
)


def _synthetic_panel(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    trend = np.linspace(0, 1.5, n)
    noise = rng.normal(0, 0.25, n)
    return pd.DataFrame(
        {
            "date": dates,
            "vix": 20 + trend * 3 + noise,
            "oil_wti": 70 + trend * 4 + noise,
            "shipping_basket": 15 + trend * 2 + noise,
            "gscpi": 1 + trend * 0.1 + noise,
            "eurusd": 1.1 + noise * 0.01,
        }
    )


def test_tune_mean_reversion_returns_params():
    y = np.cumsum(np.random.default_rng(1).normal(0, 0.05, 150))
    tuned = tune_mean_reversion_on_series(y)
    assert tuned["window"] >= 5
    assert tuned["speed"] > 0
    assert tuned["walk_forward_mae"] >= 0


def test_optimize_forecast_mae_finds_recommendation():
    panel = _synthetic_panel()
    result = optimize_forecast_mae(panel)
    assert "baseline" in result
    assert "recommended" in result
    assert result["recommended"]["walk_forward_mae"] >= 0
    assert "interpretation" in result


def test_apply_recommended_config(tmp_path, monkeypatch):
    from khukra.disruption import forecast_tuning as ft

    monkeypatch.setattr(ft, "forecast_config_path", lambda: tmp_path / "forecast_config.json")
    panel = _synthetic_panel()
    opt = optimize_forecast_mae(panel)
    cfg = apply_recommended_config(opt)
    assert cfg["production_method"] in ("mean_reversion", "holt", "bayesian_linear")
    assert cfg["smooth_days"] >= 5


def test_build_predictor_mean_reversion():
    fn = build_predictor("mean_reversion", {"window": 10, "speed": 0.15})
    y = np.array([0.1, 0.2, 0.15, 0.18, 0.22, 0.19, 0.21, 0.2, 0.23, 0.22, 0.24])
    pred = fn(y)
    assert np.isfinite(pred)
