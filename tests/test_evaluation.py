"""Tests for daily forecast-precision evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from khukra.disruption.evaluation import (
    evaluate_forecast_precision,
    save_daily_evaluation,
)
from khukra.disruption.forecasting import predict_next_holt, walk_forward_mae


def _synthetic_panel(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    trend = np.linspace(0, 2, n)
    noise = rng.normal(0, 0.3, n)
    return pd.DataFrame(
        {
            "date": dates,
            "vix": 20 + trend * 3 + noise,
            "oil_wti": 70 + trend * 5 + noise,
            "shipping_basket": 15 + trend * 2 + noise,
            "news_stress": np.clip(rng.poisson(0.3, n) * 0.5, 0, 3),
            "news_sentiment": rng.normal(-0.1, 0.2, n),
        }
    )


def test_walk_forward_scores_orders_methods():
    y = np.cumsum(np.random.default_rng(1).normal(0, 0.1, 120)) + 1.0
    mae, dir_rate = walk_forward_mae(y, predict_next_holt, min_train=40)
    assert mae >= 0
    assert 0 <= dir_rate <= 1


def test_evaluate_forecast_precision_returns_scorecard():
    panel = _synthetic_panel()
    result = evaluate_forecast_precision(panel, horizon_days=14)
    assert result["north_star"] == "forecast_precision"
    assert "hybrid" in result
    assert result["precision_score"] >= 0
    assert result["verdict"] in ("on_track", "improving", "needs_work")
    assert result["walk_forward"]["best_method"] in (
        "bayesian_linear",
        "holt",
        "naive",
        "mean_reversion",
    )
    assert "channel_ablation" in result
    assert "precision_breakdown" in result
    assert result["walk_forward"]["trace"]["point_count"] > 0
    assert len(result["walk_forward"]["trace"]["series"]) > 0


def test_evaluate_yesterday_forecast():
    from khukra.disruption.evaluation import evaluate_yesterday_forecast

    panel = _synthetic_panel()
    result = evaluate_yesterday_forecast(panel)
    assert result["forecast_method"] in ("mean_reversion", "holt", "bayesian_linear")
    assert result["verdict"] in ("hit", "close", "miss")
    assert result["error_abs"] >= 0
    assert "interpretation" in result
    assert result["yesterday_date"] < result["today_date"]


def test_save_daily_evaluation(tmp_path, monkeypatch):
    from khukra.disruption import evaluation as ev

    monkeypatch.setattr(ev, "evaluation_dir", lambda: tmp_path)
    panel = _synthetic_panel()
    result = evaluate_forecast_precision(panel)
    path = save_daily_evaluation(result)
    assert path.exists()
    assert path.name.startswith("evaluation_")


def test_evaluate_requires_history():
    panel = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=30), "vix": range(30)})
    with pytest.raises(ValueError, match="composite observations"):
        evaluate_forecast_precision(panel)
