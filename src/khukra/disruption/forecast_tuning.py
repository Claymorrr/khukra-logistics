"""Walk-forward MAE tuning for production forecast settings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from khukra.disruption.forecasting import (
    PREDICTORS,
    predict_next_mean_reversion,
    walk_forward_mae,
)
from khukra.disruption.hybrid_composite import COMPOSITE_SMOOTH_DAYS, build_hybrid_composite
from khukra.simulation.shared import data_root

PredictFn = Callable[[np.ndarray], float]

CONFIG_PATH = data_root() / "disruption_cache" / "forecast_config.json"

SMOOTH_DAYS_GRID = tuple(range(5, 16, 2))  # 5,7,9,11,13,15
MR_WINDOW_GRID = tuple(range(5, 31, 2))
MR_SPEED_GRID = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)
METHOD_GRID = ("mean_reversion", "holt", "bayesian_linear")


def forecast_config_path() -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return CONFIG_PATH


def default_forecast_config() -> dict[str, Any]:
    return {
        "production_method": "mean_reversion",
        "smooth_days": COMPOSITE_SMOOTH_DAYS,
        "mean_reversion": {"window": 15, "speed": 0.2},
    }


def load_forecast_config() -> dict[str, Any]:
    path = forecast_config_path()
    if not path.exists():
        return default_forecast_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        base = default_forecast_config()
        base.update({k: v for k, v in data.items() if k in base or k.endswith("_mae") or k.startswith("optimized")})
        if "mean_reversion" in data and isinstance(data["mean_reversion"], dict):
            base["mean_reversion"].update(data["mean_reversion"])
        return base
    except (json.JSONDecodeError, OSError):
        return default_forecast_config()


def save_forecast_config(config: dict[str, Any]) -> Path:
    path = forecast_config_path()
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def build_predictor(method: str, mean_reversion: dict[str, Any] | None = None) -> PredictFn:
    if method == "mean_reversion":
        mr = mean_reversion or {}
        window = int(mr.get("window", 15))
        speed = float(mr.get("speed", 0.2))

        def _mr(train: np.ndarray) -> float:
            return predict_next_mean_reversion(train, window=window, speed=speed)

        return _mr
    fn = PREDICTORS.get(method)
    if fn is None:
        raise ValueError(f"Unknown forecast method: {method}")
    return fn


def _score_predictor(y: np.ndarray, predict_fn: PredictFn) -> tuple[float, float]:
    return walk_forward_mae(y, predict_fn)


def tune_mean_reversion_on_series(y: np.ndarray) -> dict[str, Any]:
    """Grid-search mean-reversion window/speed on a fixed composite series."""
    best_mae = float("inf")
    best: dict[str, Any] = {"window": 15, "speed": 0.2, "walk_forward_mae": best_mae, "direction_hit_rate": 0.0}
    for window in MR_WINDOW_GRID:
        for speed in MR_SPEED_GRID:
            fn = build_predictor("mean_reversion", {"window": window, "speed": speed})
            mae, dir_rate = _score_predictor(y, fn)
            if mae < best_mae:
                best_mae = mae
                best = {
                    "window": window,
                    "speed": speed,
                    "walk_forward_mae": round(mae, 4),
                    "direction_hit_rate": round(dir_rate, 4),
                }
    return best


def optimize_forecast_mae(panel: pd.DataFrame) -> dict[str, Any]:
    """Search smooth days, method, and mean-reversion params for lowest walk-forward MAE."""
    baseline_cfg = default_forecast_config()
    baseline_smooth, _ = build_hybrid_composite(panel, smooth_days=baseline_cfg["smooth_days"])
    baseline_fn = build_predictor(
        baseline_cfg["production_method"],
        baseline_cfg["mean_reversion"],
    )
    baseline_mae, baseline_dir = _score_predictor(baseline_smooth.values, baseline_fn)

    best: dict[str, Any] = {
        "smooth_days": baseline_cfg["smooth_days"],
        "production_method": baseline_cfg["production_method"],
        "mean_reversion": dict(baseline_cfg["mean_reversion"]),
        "walk_forward_mae": baseline_mae,
        "direction_hit_rate": baseline_dir,
    }

    method_scores_snapshot: dict[str, dict[str, float]] = {}

    for smooth_days in SMOOTH_DAYS_GRID:
        try:
            smooth, _ = build_hybrid_composite(panel, smooth_days=smooth_days)
        except ValueError:
            continue
        if len(smooth) < 80:
            continue
        y = smooth.values

        for method in METHOD_GRID:
            if method == "mean_reversion":
                tuned = tune_mean_reversion_on_series(y)
                fn = build_predictor("mean_reversion", tuned)
                mae, dir_rate = tuned["walk_forward_mae"], tuned["direction_hit_rate"]
                mr_params = {"window": tuned["window"], "speed": tuned["speed"]}
            else:
                fn = build_predictor(method)
                mae, dir_rate = _score_predictor(y, fn)
                mr_params = {"window": 15, "speed": 0.2}

            method_scores_snapshot[f"sd{smooth_days}_{method}"] = {
                "walk_forward_mae": round(float(mae), 4),
                "direction_hit_rate": round(float(dir_rate), 4),
            }

            if mae < best["walk_forward_mae"]:
                best = {
                    "smooth_days": smooth_days,
                    "production_method": method,
                    "mean_reversion": mr_params,
                    "walk_forward_mae": float(mae),
                    "direction_hit_rate": float(dir_rate),
                }

    improvement = baseline_mae - best["walk_forward_mae"]
    pct = (improvement / baseline_mae * 100) if baseline_mae > 0 else 0.0

    return {
        "optimized_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "smooth_days": baseline_cfg["smooth_days"],
            "production_method": baseline_cfg["production_method"],
            "mean_reversion": baseline_cfg["mean_reversion"],
            "walk_forward_mae": round(baseline_mae, 4),
            "direction_hit_rate": round(baseline_dir, 4),
        },
        "recommended": {
            "smooth_days": best["smooth_days"],
            "production_method": best["production_method"],
            "mean_reversion": best["mean_reversion"],
            "walk_forward_mae": round(best["walk_forward_mae"], 4),
            "direction_hit_rate": round(best["direction_hit_rate"], 4),
        },
        "improvement_abs": round(improvement, 4),
        "improvement_pct": round(pct, 1),
        "beats_baseline": improvement > 0.001,
        "mae_target": 0.38,
        "beats_mae_target": best["walk_forward_mae"] <= 0.38,
        "search_grid": {
            "smooth_days": list(SMOOTH_DAYS_GRID),
            "mean_reversion_windows": list(MR_WINDOW_GRID),
            "mean_reversion_speeds": list(MR_SPEED_GRID),
            "methods": list(METHOD_GRID),
        },
        "top_candidates": sorted(
            [
                {"key": k, **v}
                for k, v in method_scores_snapshot.items()
            ],
            key=lambda row: row["walk_forward_mae"],
        )[:6],
        "interpretation": _optimization_interpretation(baseline_mae, best, improvement, pct),
    }


def _optimization_interpretation(
    baseline_mae: float,
    best: dict[str, Any],
    improvement: float,
    pct: float,
) -> str:
    if improvement <= 0.001:
        return (
            f"Current settings are already near-optimal on walk-forward MAE ({baseline_mae:.3f}σ). "
            "Focus on data quality (refresh macro/news) or channel ablation rather than model params."
        )
    mr = best["mean_reversion"]
    extra = ""
    if best["production_method"] == "mean_reversion":
        extra = f" Mean-reversion window={mr['window']}, speed={mr['speed']}."
    return (
        f"Tuning can lower walk-forward MAE from {baseline_mae:.3f}σ to {best['walk_forward_mae']:.3f}σ "
        f"({improvement:.3f}σ / {pct:.0f}% better) using {best['smooth_days']}-day smooth, "
        f"{best['production_method']}.{extra} Apply recommended settings to update production forecasts."
    )


def apply_recommended_config(optimization: dict[str, Any]) -> dict[str, Any]:
    """Persist recommended settings for production forecasting."""
    rec = optimization["recommended"]
    config = {
        "optimized_at": optimization["optimized_at"],
        "production_method": rec["production_method"],
        "smooth_days": rec["smooth_days"],
        "mean_reversion": rec["mean_reversion"],
        "walk_forward_mae": rec["walk_forward_mae"],
        "direction_hit_rate": rec["direction_hit_rate"],
        "baseline_mae": optimization["baseline"]["walk_forward_mae"],
    }
    save_forecast_config(config)
    return config
