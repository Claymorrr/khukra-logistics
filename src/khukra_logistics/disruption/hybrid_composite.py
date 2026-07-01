"""Hybrid composite index tuned for forecast precision.

Channel weights reflect ablation: macro and market carry predictive mass; news is
kept at low weight until NLP/feed quality improves (ops-015+).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from khukra_logistics.disruption.catalog import get_signal, hybrid_channel

# Production smoothing — tuned on walk-forward precision (ops-025)
COMPOSITE_SMOOTH_DAYS = 9

SPARSE_SIGNALS = frozenset({"news_stress", "news_sentiment"})

# Default channel mix for precision mode (sum = 1.0)
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "macro": 0.50,
    "market": 0.42,
    "news": 0.08,
}

ROLLING_Z_WINDOW = 60
ROLLING_Z_MIN_PERIODS = 20


def _zscore_series(series: pd.Series, window: int = ROLLING_Z_WINDOW) -> pd.Series:
    mean = series.rolling(window, min_periods=ROLLING_Z_MIN_PERIODS).mean()
    std = series.rolling(window, min_periods=ROLLING_Z_MIN_PERIODS).std().replace(0, np.nan)
    return (series - mean) / std


def _inverse_variance_combine(frames: list[pd.Series]) -> pd.Series:
    """Combine z-scored signals with static inverse-variance weights."""
    if len(frames) == 1:
        return frames[0]
    df = pd.concat(frames, axis=1)
    variances = df.apply(lambda col: col.dropna().var())
    inv = variances.replace(0, np.nan).rpow(-1).fillna(0.0)
    if inv.sum() <= 0:
        return df.mean(axis=1, skipna=True)

    def _weighted_row(row: pd.Series) -> float:
        mask = row.notna()
        if not mask.any():
            return float("nan")
        cols = row.index[mask]
        weights = inv[cols]
        if weights.sum() <= 0:
            return float(row[mask].mean())
        weights = weights / weights.sum()
        return float(np.dot(row[mask].astype(float), weights.values))

    return df.apply(_weighted_row, axis=1)


def build_hybrid_composite(
    panel: pd.DataFrame,
    signal_cols: list[str] | None = None,
    channel_weights: dict[str, float] | None = None,
    smooth_days: int = 0,
) -> tuple[pd.Series, dict[str, Any]]:
    """Weighted z-score composite across macro / market / news channels."""
    cols = signal_cols or [c for c in panel.columns if c != "date"]
    weights = channel_weights or DEFAULT_CHANNEL_WEIGHTS
    work = panel.copy()

    for sparse in SPARSE_SIGNALS:
        if sparse in work.columns:
            work[sparse] = work[sparse].fillna(0.0)

    channel_frames: dict[str, list[pd.Series]] = {"macro": [], "market": [], "news": []}
    for col in cols:
        if col not in work.columns or work[col].notna().sum() < 30:
            continue
        sig = get_signal(col)
        ch = hybrid_channel(sig) if sig else "macro"
        z = _zscore_series(work[col]).rename(col)
        channel_frames[ch].append(z)

    channel_series: dict[str, pd.Series] = {}
    active_weights: dict[str, float] = {}
    for ch, frames in channel_frames.items():
        if not frames:
            continue
        channel_series[ch] = _inverse_variance_combine(frames)
        active_weights[ch] = weights.get(ch, 0.0)

    if not channel_series:
        raise ValueError("Insufficient history to compute hybrid composite.")

    weight_sum = sum(active_weights.values()) or 1.0
    channel_df = pd.DataFrame(channel_series)
    weights_series = pd.Series({ch: active_weights[ch] / weight_sum for ch in channel_series})

    def _weighted_row(row: pd.Series) -> float:
        mask = row.notna()
        if not mask.any():
            return float("nan")
        w = weights_series[mask]
        w = w / w.sum()
        return float(np.average(row[mask].astype(float), weights=w.values))

    composite = channel_df.apply(_weighted_row, axis=1).dropna()

    if smooth_days > 1:
        composite = composite.rolling(smooth_days, min_periods=1).mean().dropna()

    meta = {
        "mode": "hybrid_inverse_variance",
        "channel_weights": {ch: round(active_weights[ch] / weight_sum, 3) for ch in active_weights},
        "signals_per_channel": {ch: len(channel_frames[ch]) for ch in channel_frames if channel_frames[ch]},
        "smooth_days": smooth_days,
    }
    return composite, meta
