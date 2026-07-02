"""Forecast method selection and one-step predictors for composite precision."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from khukra.disruption.bayesian import bayesian_linear_forecast
from khukra.simulation.primitives import forecast_holt_linear

PredictFn = Callable[[np.ndarray], float]

EVAL_TAIL = 504  # ~2y trading days for walk-forward scoring
EVAL_STRIDE = 2  # speed: score every 2nd step on long histories


def predict_next_bayesian(train: np.ndarray) -> float:
    return float(bayesian_linear_forecast(train, horizon=1)["forecast"][0])


def predict_next_holt(train: np.ndarray) -> float:
    future, _, _ = forecast_holt_linear(train, horizon=1)
    return float(future[0])


def predict_next_naive(train: np.ndarray) -> float:
    return float(train[-1])


def predict_next_mean_reversion(train: np.ndarray, window: int = 15, speed: float = 0.2) -> float:
    """Pull forecast toward recent mean — often best for z-score composites."""
    tail = train[-window:] if len(train) >= window else train
    mu = float(np.mean(tail))
    return float(train[-1] + speed * (mu - train[-1]))


PRODUCTION_METHOD = "mean_reversion"

PREDICTORS: dict[str, PredictFn] = {
    "holt": predict_next_holt,
    "mean_reversion": predict_next_mean_reversion,
    "bayesian_linear": predict_next_bayesian,
    "naive": predict_next_naive,
}

# Fast scoring for API paths that must not run expensive Bayesian walk-forward.
FAST_SCORE_METHODS: tuple[str, ...] = ("holt", PRODUCTION_METHOD)


def walk_forward_mae(
    y: np.ndarray,
    predict_fn: PredictFn,
    min_train: int = 60,
    tail: int = EVAL_TAIL,
    stride: int = EVAL_STRIDE,
) -> tuple[float, float]:
    """Return (mae, direction_hit_rate) on tail window."""
    y = np.asarray(y, dtype=float)
    if len(y) > tail:
        offset = len(y) - tail
        y = y[offset:]
        min_train = max(40, min_train - offset)

    errors: list[float] = []
    direction_hits = 0
    direction_total = 0
    indices = range(min_train, len(y), max(1, stride))

    for t in indices:
        train = y[:t]
        pred = predict_fn(train)
        actual = float(y[t])
        errors.append(abs(actual - pred))
        if t > min_train:
            actual_delta = actual - float(y[t - 1])
            pred_delta = pred - float(y[t - 1])
            if abs(actual_delta) > 1e-9:
                direction_total += 1
                if np.sign(actual_delta) == np.sign(pred_delta):
                    direction_hits += 1

    mae = float(np.mean(errors)) if errors else float("nan")
    dir_rate = float(direction_hits / direction_total) if direction_total else 0.0
    return mae, dir_rate


def walk_forward_trace(
    y: np.ndarray,
    dates: pd.Series | np.ndarray,
    method: str,
    min_train: int = 60,
    tail: int = EVAL_TAIL,
    stride: int = EVAL_STRIDE,
    max_points: int = 126,
) -> dict[str, Any]:
    """Return actual vs predicted points for walk-forward visualization."""
    y = np.asarray(y, dtype=float)
    dt = pd.to_datetime(dates)
    if len(y) != len(dt):
        raise ValueError("y and dates must have the same length")

    if len(y) > tail:
        offset = len(y) - tail
        y = y[offset:]
        dt = dt.iloc[offset:].reset_index(drop=True)
        min_train = max(40, min_train - offset)

    fn = PREDICTORS.get(method, predict_next_holt)
    points: list[dict[str, Any]] = []
    for t in range(min_train, len(y), max(1, stride)):
        pred = float(fn(y[:t]))
        actual = float(y[t])
        dir_ok: bool | None = None
        if t > min_train and abs(y[t] - y[t - 1]) > 1e-9:
            dir_ok = bool(np.sign(actual - y[t - 1]) == np.sign(pred - y[t - 1]))
        points.append(
            {
                "date": pd.Timestamp(dt.iloc[t]).strftime("%Y-%m-%d"),
                "actual": round(actual, 4),
                "predicted": round(pred, 4),
                "abs_error": round(abs(actual - pred), 4),
                "direction_correct": dir_ok,
            }
        )

    if len(points) > max_points:
        step = max(1, len(points) // max_points)
        points = points[::step]

    return {
        "method": method,
        "eval_window_days": tail,
        "stride": stride,
        "point_count": len(points),
        "series": points,
    }


def score_methods(
    y: np.ndarray,
    methods: tuple[str, ...] | None = None,
    min_train: int = 60,
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for name in methods or tuple(PREDICTORS.keys()):
        fn = PREDICTORS[name]
        mae, dir_rate = walk_forward_mae(y, fn, min_train=min_train)
        scores[name] = {
            "walk_forward_mae": round(mae, 4),
            "direction_hit_rate": round(dir_rate, 4),
        }
    return scores


def select_best_method(y: np.ndarray, min_train: int = 60) -> tuple[str, dict[str, dict[str, float]]]:
    """Pick lowest walk-forward MAE method on recent tail (naive excluded from production)."""
    scores = score_methods(y, min_train=min_train)
    production = {k: v for k, v in scores.items() if k != "naive"}
    best = min(production, key=lambda k: production[k]["walk_forward_mae"])
    return best, scores


def score_methods_fast(y: np.ndarray, min_train: int = 60) -> dict[str, dict[str, float]]:
    """Holt + mean reversion only — for low-latency forecast endpoints."""
    return score_methods(y, methods=FAST_SCORE_METHODS, min_train=min_train)


def forecast_horizon(
    y: np.ndarray,
    horizon: int,
    method: str | None = None,
    predict_fn: PredictFn | None = None,
) -> dict[str, list[float]]:
    """Project `horizon` steps using recursive one-step predictions."""
    y = np.asarray(y, dtype=float).copy()
    fn = predict_fn or PREDICTORS.get(method or PRODUCTION_METHOD, predict_next_holt)
    preds: list[float] = []
    for _ in range(horizon):
        nxt = fn(y)
        preds.append(nxt)
        y = np.append(y, nxt)
    # Simple symmetric band from recent residuals
    if len(y) > 30:
        resid = np.diff(y[-60:])
        sd = float(np.std(resid)) if len(resid) else 0.15
    else:
        sd = 0.15
    lower = [p - 1.96 * sd for p in preds]
    upper = [p + 1.96 * sd for p in preds]
    return {"forecast": preds, "forecast_lower": lower, "forecast_upper": upper}


def get_production_smooth_days() -> int:
    from khukra.disruption.forecast_tuning import load_forecast_config

    return int(load_forecast_config().get("smooth_days", 9))


def get_production_method() -> str:
    from khukra.disruption.forecast_tuning import load_forecast_config

    return str(load_forecast_config().get("production_method", PRODUCTION_METHOD))


def get_production_predictor() -> PredictFn:
    from khukra.disruption.forecast_tuning import build_predictor, load_forecast_config

    cfg = load_forecast_config()
    return build_predictor(
        str(cfg.get("production_method", PRODUCTION_METHOD)),
        cfg.get("mean_reversion"),
    )
