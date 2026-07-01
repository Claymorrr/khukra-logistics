"""Forecast method selection and one-step predictors for composite precision."""

from __future__ import annotations

from typing import Callable

import numpy as np

from khukra_logistics.disruption.bayesian import bayesian_linear_forecast
from khukra_logistics.simulation.primitives import forecast_holt_linear

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


PREDICTORS: dict[str, PredictFn] = {
    "holt": predict_next_holt,
    "mean_reversion": predict_next_mean_reversion,
    "bayesian_linear": predict_next_bayesian,
    "naive": predict_next_naive,
}


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


def select_best_method(y: np.ndarray, min_train: int = 60) -> tuple[str, dict[str, dict[str, float]]]:
    """Pick lowest walk-forward MAE method on recent tail (naive excluded from production)."""
    scores: dict[str, dict[str, float]] = {}
    for name, fn in PREDICTORS.items():
        mae, dir_rate = walk_forward_mae(y, fn, min_train=min_train)
        scores[name] = {
            "walk_forward_mae": round(mae, 4),
            "direction_hit_rate": round(dir_rate, 4),
        }
    production = {k: v for k, v in scores.items() if k != "naive"}
    best = min(production, key=lambda k: production[k]["walk_forward_mae"])
    return best, scores


def forecast_horizon(y: np.ndarray, horizon: int, method: str) -> dict[str, list[float]]:
    """Project `horizon` steps using recursive one-step predictions."""
    y = np.asarray(y, dtype=float).copy()
    fn = PREDICTORS.get(method, predict_next_holt)
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
