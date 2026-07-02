"""Daily forecast-precision evaluation for the hybrid disruption panel."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from khukra.disruption.bayesian import bayesian_linear_forecast
from khukra.disruption.catalog import DISRUPTION_SIGNALS, get_signal, hybrid_channel
from khukra.disruption.forecasting import (
    PREDICTORS,
    PRODUCTION_METHOD,
    get_production_method,
    get_production_predictor,
    get_production_smooth_days,
    select_best_method,
    walk_forward_mae,
    walk_forward_trace,
)
from khukra.disruption.hybrid_composite import build_hybrid_composite
from khukra.simulation.shared import data_root

MIN_TRAIN = 60
MAE_TARGET = 0.38  # tightened after weighted composite + model selection


def evaluation_dir() -> Path:
    path = data_root() / "disruption_cache" / "evaluation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _hybrid_breakdown(panel: pd.DataFrame) -> dict[str, Any]:
    cols = [c for c in panel.columns if c != "date"]
    by_channel: dict[str, list[str]] = {"macro": [], "market": [], "news": []}
    for col in cols:
        sig = get_signal(col)
        ch = hybrid_channel(sig) if sig else "macro"
        by_channel[ch].append(col)
    _, meta = build_hybrid_composite(panel, cols, smooth_days=0)
    return {
        "channels": {
            ch: {"signal_ids": ids, "active_count": len(ids)}
            for ch, ids in by_channel.items()
        },
        "hybrid_mode": meta.get("mode", "hybrid_weighted"),
        "channel_weights": meta.get("channel_weights", {}),
        "total_signals": len(cols),
    }


def _leave_channel_out_mae(panel: pd.DataFrame, y_full: np.ndarray) -> dict[str, float]:
    scores: dict[str, float] = {}
    all_cols = [c for c in panel.columns if c != "date"]
    best_method, _ = select_best_method(y_full)

    for channel in ("macro", "market", "news"):
        drop = {s.signal_id for s in DISRUPTION_SIGNALS if hybrid_channel(s) == channel}
        keep = [c for c in all_cols if c not in drop]
        if len(keep) < 2:
            continue
        try:
            reduced, _ = build_hybrid_composite(panel, keep, smooth_days=get_production_smooth_days())
            if len(reduced) < MIN_TRAIN + 5:
                continue
            mae, _ = walk_forward_mae(reduced.values, PREDICTORS[best_method])
            scores[f"without_{channel}_mae"] = round(mae, 4)
        except ValueError:
            continue

    full_mae, _ = walk_forward_mae(y_full, PREDICTORS[best_method])
    scores["full_hybrid_mae"] = round(full_mae, 4)
    for channel in ("macro", "market", "news"):
        key = f"without_{channel}_mae"
        if key in scores:
            scores[f"{channel}_lift"] = round(scores[key] - full_mae, 4)
    return scores


def _precision_breakdown(best_mae: float, holt_mae: float, direction_hit_rate: float) -> dict[str, float]:
    mae_component = max(0.0, min(1.0, 1.0 - best_mae / 0.65))
    beat_bonus = 0.12 if best_mae <= holt_mae + 0.005 else 0.0
    target_bonus = 0.08 if best_mae <= MAE_TARGET else 0.0
    raw = 0.50 * mae_component + 0.30 * direction_hit_rate + beat_bonus + target_bonus
    return {
        "mae_component": round(mae_component, 4),
        "mae_weighted": round(0.50 * mae_component, 4),
        "direction_hit_rate": round(direction_hit_rate, 4),
        "direction_weighted": round(0.30 * direction_hit_rate, 4),
        "beat_holt_bonus": beat_bonus,
        "mae_target_bonus": target_bonus,
        "raw_total": round(raw, 4),
        "mae_target": MAE_TARGET,
        "mae_ceiling": 0.65,
    }


def _precision_score(best_mae: float, holt_mae: float, direction_hit_rate: float) -> int:
    mae_component = max(0.0, min(1.0, 1.0 - best_mae / 0.65))
    beat_bonus = 0.12 if best_mae <= holt_mae + 0.005 else 0.0
    target_bonus = 0.08 if best_mae <= MAE_TARGET else 0.0
    raw = 0.50 * mae_component + 0.30 * direction_hit_rate + beat_bonus + target_bonus
    return int(round(max(0.0, min(1.0, raw)) * 100))


def _verdict(best_mae: float, holt_mae: float, direction_hit_rate: float) -> str:
    if best_mae <= MAE_TARGET and direction_hit_rate >= 0.55:
        return "on_track"
    if best_mae <= holt_mae + 0.02 or direction_hit_rate >= 0.52:
        return "improving"
    return "needs_work"


def evaluate_forecast_precision(
    panel: pd.DataFrame,
    horizon_days: int = 30,
) -> dict[str, Any]:
    """Run daily precision measurement on the weighted hybrid composite."""
    smooth, hybrid_meta = build_hybrid_composite(panel, smooth_days=get_production_smooth_days())
    y = smooth.values
    dates = panel.loc[smooth.index, "date"]
    if len(y) < MIN_TRAIN + 10:
        raise ValueError(f"Need at least {MIN_TRAIN + 10} composite observations for evaluation.")

    best_name, wf = select_best_method(y)
    best = wf[best_name]
    holt_mae = wf["holt"]["walk_forward_mae"]
    trace = walk_forward_trace(y, dates, best_name)

    holdout = bayesian_linear_forecast(y, horizon=horizon_days)
    channel_mae = _leave_channel_out_mae(panel, y)

    breakdown = _precision_breakdown(best["walk_forward_mae"], holt_mae, best["direction_hit_rate"])
    precision = _precision_score(best["walk_forward_mae"], holt_mae, best["direction_hit_rate"])
    verdict = _verdict(best["walk_forward_mae"], holt_mae, best["direction_hit_rate"])

    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_date": date.today().isoformat(),
        "north_star": "forecast_precision",
        "hybrid": _hybrid_breakdown(panel),
        "hybrid_composite": hybrid_meta,
        "horizon_days": horizon_days,
        "walk_forward": {
            "methods": wf,
            "best_method": best_name,
            "beats_holt": bool(best["walk_forward_mae"] <= holt_mae + 0.005),
            "beats_naive": bool(best["walk_forward_mae"] < wf["naive"]["walk_forward_mae"]),
            "eval_window_days": 504,
            "trace": trace,
        },
        "precision_breakdown": breakdown,
        "holdout_horizon": {
            "mae": holdout["holdout_mae"],
            "rmse": holdout["holdout_rmse"],
            "credible_level": holdout["credible_level"],
        },
        "channel_ablation": channel_mae,
        "precision_score": precision,
        "verdict": verdict,
        "mae_target": MAE_TARGET,
        "interpretation": _interpretation(best_name, best, holt_mae, verdict, precision, channel_mae),
        "composite_observations": int(len(y)),
    }


def _interpretation(
    best_name: str,
    best: dict[str, float],
    holt_mae: float,
    verdict: str,
    precision: int,
    channel_mae: dict[str, float],
) -> str:
    parts = [
        f"Daily precision score {precision}/100 ({verdict.replace('_', ' ')}). "
        f"Production model: {best_name} "
        f"(2y walk-forward MAE={best['walk_forward_mae']:.3f}, "
        f"direction hit rate={best['direction_hit_rate']:.0%}). "
        f"Holt benchmark MAE={holt_mae:.3f}."
    ]
    lifts = [
        (ch, channel_mae[f"{ch}_lift"])
        for ch in ("news", "macro", "market")
        if f"{ch}_lift" in channel_mae
    ]
    if lifts:
        helpful = [ch for ch, lift in lifts if lift > 0.01]
        harmful = [ch for ch, lift in lifts if lift < -0.01]
        if helpful:
            parts.append(f"Channels helping precision: {', '.join(helpful)}.")
        if harmful:
            parts.append(f"Channels hurting precision: {', '.join(harmful)} — lower weight or improve feeds.")
    return " ".join(parts)


def save_daily_evaluation(result: dict[str, Any]) -> Path:
    eval_date = result.get("evaluation_date", date.today().isoformat())
    path = evaluation_dir() / f"evaluation_{eval_date}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path


def load_evaluation_history(days: int = 30) -> list[dict[str, Any]]:
    root = evaluation_dir()
    files = sorted(root.glob("evaluation_*.json"), reverse=True)
    rows: list[dict[str, Any]] = []
    for path in files[:days]:
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return rows


def latest_evaluation() -> dict[str, Any] | None:
    history = load_evaluation_history(days=1)
    return history[0] if history else None


def _direction_match(actual_delta: float, pred_delta: float) -> bool:
    if abs(actual_delta) <= 1e-9:
        return True
    if abs(pred_delta) <= 1e-9:
        return False
    return (actual_delta > 0) == (pred_delta > 0)


def _yesterday_step_interpretation(
    *,
    forecast_method: str,
    yesterday_date: str,
    today_date: str,
    predicted: float,
    actual: float,
    error_abs: float,
    direction_correct: bool,
    actual_change: float,
    predicted_change: float,
) -> str:
    level = "strong" if error_abs <= MAE_TARGET / 2 else "good" if error_abs <= MAE_TARGET else "weak"
    dir_phrase = "Direction correct" if direction_correct else "Direction missed"
    move_actual = "rose" if actual_change > 0 else "fell" if actual_change < 0 else "was flat"
    move_pred = "rise" if predicted_change > 0 else "fall" if predicted_change < 0 else "stay flat"
    return (
        f"From {yesterday_date}, {forecast_method} forecast {today_date} at {predicted:+.2f}σ "
        f"vs realized {actual:+.2f}σ ({level} level call, error {error_abs:.2f}σ; target ≤{MAE_TARGET}). "
        f"Stress {move_actual} {abs(actual_change):.2f}σ; model expected a {move_pred} "
        f"({abs(predicted_change):.2f}σ). {dir_phrase}."
    )


def evaluate_yesterday_forecast(panel: pd.DataFrame) -> dict[str, Any]:
    """Score the latest 1-step production forecast against today's realized composite."""
    smooth, hybrid_meta = build_hybrid_composite(panel, smooth_days=get_production_smooth_days())
    raw, _ = build_hybrid_composite(panel, smooth_days=0)
    if len(smooth) < 2:
        raise ValueError("Need at least two composite observations for yesterday forecast check.")

    y = smooth.values.astype(float)
    dates = panel.loc[smooth.index, "date"]
    t = len(y) - 1
    train = y[:t]
    actual_today = float(y[t])
    predicted_today = float(get_production_predictor()(train))
    actual_yesterday = float(y[t - 1])
    raw_today = float(raw.iloc[-1])

    error_abs = abs(actual_today - predicted_today)
    error_signed = actual_today - predicted_today
    actual_change = actual_today - actual_yesterday
    predicted_change = predicted_today - actual_yesterday
    direction_correct = _direction_match(actual_change, predicted_change)

    if error_abs <= MAE_TARGET and direction_correct:
        verdict = "hit"
    elif error_abs <= MAE_TARGET:
        verdict = "close"
    else:
        verdict = "miss"

    yesterday_date = pd.Timestamp(dates.iloc[t - 1]).strftime("%Y-%m-%d")
    today_date = pd.Timestamp(dates.iloc[t]).strftime("%Y-%m-%d")

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "forecast_method": get_production_method(),
        "target": "smoothed_composite",
        "smooth_days": get_production_smooth_days(),
        "hybrid_mode": hybrid_meta.get("mode"),
        "yesterday_date": yesterday_date,
        "today_date": today_date,
        "yesterday_smoothed": round(actual_yesterday, 4),
        "predicted_today": round(predicted_today, 4),
        "actual_today_smoothed": round(actual_today, 4),
        "actual_today_raw": round(raw_today, 4),
        "error_abs": round(error_abs, 4),
        "error_signed": round(error_signed, 4),
        "actual_change": round(actual_change, 4),
        "predicted_change": round(predicted_change, 4),
        "direction_correct": direction_correct,
        "beat_mae_target": error_abs <= MAE_TARGET,
        "mae_target": MAE_TARGET,
        "verdict": verdict,
        "interpretation": _yesterday_step_interpretation(
            forecast_method=get_production_method(),
            yesterday_date=yesterday_date,
            today_date=today_date,
            predicted=predicted_today,
            actual=actual_today,
            error_abs=error_abs,
            direction_correct=direction_correct,
            actual_change=actual_change,
            predicted_change=predicted_change,
        ),
    }
