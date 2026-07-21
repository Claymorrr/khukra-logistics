"""Hybrid composite index tuned for forecast precision.

Channel weights reflect ablation: macro and market carry predictive mass; news is
kept at low weight until NLP/feed quality improves (ops-015+).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from khukra.disruption.catalog import get_signal, hybrid_channel
from khukra.disruption.bayesian import composite_posterior

# Production smoothing — tuned on walk-forward precision (ops-025)
COMPOSITE_SMOOTH_DAYS = 9

SPARSE_SIGNALS = frozenset(
    {
        "news_stress",
        "news_sentiment",
        "news_suez_mentions",
        "news_panama_mentions",
        "news_carrier_mentions",
        "news_port_mentions",
    }
)

# Default channel mix for precision mode (sum = 1.0)
DEFAULT_CHANNEL_WEIGHTS: dict[str, float] = {
    "macro": 0.50,
    "market": 0.42,
    "news": 0.08,
}

ROLLING_Z_WINDOW = 60
ROLLING_Z_MIN_PERIODS = 20

REGIME_BANDS = (
    ("calm", -float("inf"), -0.5, "Calm", "Stress is below recent norms across the hybrid panel."),
    ("neutral", -0.5, 0.5, "Neutral", "Stress is near its 60-day average — no strong directional signal."),
    ("watch", 0.5, 1.5, "Watch", "Stress is building above recent norms — worth monitoring."),
    ("elevated", 1.5, float("inf"), "Elevated", "Stress is materially above recent norms."),
)


def _regime_for_z(z: float) -> tuple[str, str, str]:
    for regime_id, lo, hi, label, detail in REGIME_BANDS:
        if lo <= z < hi:
            return regime_id, label, detail
    return "elevated", "Elevated", REGIME_BANDS[-1][4]


def _build_interpretation(
    panel: pd.DataFrame,
    composite_raw: pd.Series,
    composite_smoothed: pd.Series,
    signal_meta: list[dict[str, Any]],
    channel_detail: dict[str, Any],
    norm_ch_weights: dict[str, float],
    contributions: dict[str, float],
    composite_value: float,
    smoothed_value: float,
    n_signals: int,
) -> dict[str, Any]:
    """Plain-language and contextual interpretation for the composite index."""
    from scipy import stats as sp_stats

    clean = composite_raw.dropna()
    post = composite_posterior(composite_value, n_signals, int(len(clean)))
    percentile = float(sp_stats.percentileofscore(clean, composite_value)) if len(clean) else 50.0
    p10 = float(np.percentile(clean, 10)) if len(clean) else -0.5
    p90 = float(np.percentile(clean, 90)) if len(clean) else 1.5

    regime_id, regime_label, regime_detail = _regime_for_z(composite_value)
    smooth_regime_id, smooth_regime_label, _ = _regime_for_z(smoothed_value)

    drivers: list[dict[str, Any]] = []
    for s in signal_meta:
        ch = s["channel"]
        w_ch = norm_ch_weights.get(ch, 0.0)
        w_sig = s.get("weight_in_channel") or 0.0
        impact = w_ch * w_sig * s["z_score"]
        if abs(impact) < 0.01:
            continue
        drivers.append(
            {
                "signal_id": s["signal_id"],
                "label": s["label"],
                "channel": ch,
                "impact": round(impact, 4),
                "direction": "up" if impact > 0 else "down",
                "z_score": s["z_score"],
            }
        )
    drivers.sort(key=lambda d: abs(d["impact"]), reverse=True)

    channel_rank = sorted(
        ((ch, contributions.get(ch, 0.0)) for ch in contributions),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    channel_bits: list[str] = []
    for ch, contrib in channel_rank[:2]:
        if abs(contrib) < 0.05:
            continue
        verb = "pushing stress up" if contrib > 0 else "pulling stress down"
        channel_bits.append(f"{ch} ({verb}, {contrib:+.2f}σ)")

    driver_bits: list[str] = []
    for d in drivers[:3]:
        driver_bits.append(f"{d['label']} ({d['impact']:+.2f}σ)")

    headline_parts = [
        f"Hybrid disruption index at {composite_value:+.2f}σ ({regime_label.lower()}).",
        f"Smoothed production level {smoothed_value:+.2f}σ ({smooth_regime_label.lower()}).",
        f"Historical percentile {percentile:.0f} (vs full cached sample).",
    ]
    if channel_bits:
        headline_parts.append(f"Main channels: {'; '.join(channel_bits)}.")
    if driver_bits:
        headline_parts.append(f"Top drivers: {', '.join(driver_bits)}.")

    recent_n = min(90, len(composite_raw))
    raw_tail = composite_raw.iloc[-recent_n:]
    smooth_tail = composite_smoothed.iloc[-recent_n:]
    idx = raw_tail.index

    return {
        "regime": regime_id,
        "regime_label": regime_label,
        "regime_detail": regime_detail,
        "smoothed_regime": smooth_regime_id,
        "smoothed_regime_label": smooth_regime_label,
        "headline": " ".join(headline_parts),
        "percentile_rank": round(percentile, 1),
        "prob_elevated": round(post["prob_elevated"], 4),
        "ci_low": round(post["ci_low"], 4),
        "ci_high": round(post["ci_high"], 4),
        "p10": round(p10, 4),
        "p90": round(p90, 4),
        "vs_zero": round(composite_value, 4),
        "smoothed_vs_zero": round(smoothed_value, 4),
        "top_drivers": drivers[:5],
        "channel_rank": [{"channel": ch, "contribution": round(v, 4)} for ch, v in channel_rank],
        "bands": [
            {"id": r, "label": lbl, "from": lo if lo > -1e6 else -2.5, "to": hi if hi < 1e6 else 2.5}
            for r, lo, hi, lbl, _ in REGIME_BANDS
        ],
        "series_recent": {
            "dates": panel.loc[idx, "date"].dt.strftime("%Y-%m-%d").tolist(),
            "composite_z": [round(float(v), 4) for v in raw_tail.tolist()],
            "composite_smoothed": [round(float(v), 4) for v in smooth_tail.tolist()],
        },
    }


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


def _inverse_variance_weights(frames: list[pd.Series]) -> dict[str, float]:
    """Per-signal weights used inside a channel (static inverse variance)."""
    if len(frames) == 1:
        name = frames[0].name or "signal"
        return {str(name): 1.0}
    df = pd.concat(frames, axis=1)
    variances = df.apply(lambda col: col.dropna().var())
    inv = variances.replace(0, np.nan).rpow(-1).fillna(0.0)
    if inv.sum() <= 0:
        w = pd.Series(1.0 / len(df.columns), index=df.columns)
    else:
        w = inv / inv.sum()
    return {str(k): round(float(v), 4) for k, v in w.items()}


def decompose_hybrid_index(panel: pd.DataFrame) -> dict[str, Any]:
    """Mathematical breakdown of the hybrid index at the latest observation."""
    cols = [c for c in panel.columns if c != "date"]
    weights = DEFAULT_CHANNEL_WEIGHTS
    work = panel.copy()

    for sparse in SPARSE_SIGNALS:
        if sparse in work.columns:
            work[sparse] = work[sparse].fillna(0.0)

    z_frames: dict[str, pd.Series] = {}
    channel_frames: dict[str, list[pd.Series]] = {"macro": [], "market": [], "news": []}
    signal_meta: list[dict[str, Any]] = []

    for col in cols:
        if col not in work.columns or work[col].notna().sum() < 30:
            continue
        sig = get_signal(col)
        ch = hybrid_channel(sig) if sig else "macro"
        raw = work[col]
        z = _zscore_series(raw).rename(col)
        z_frames[col] = z
        channel_frames[ch].append(z)
        last_i = z.last_valid_index()
        if last_i is None:
            continue
        signal_meta.append(
            {
                "signal_id": col,
                "label": sig.label if sig else col,
                "channel": ch,
                "raw_value": round(float(raw.loc[last_i]), 4),
                "rolling_mean_60": round(float(raw.rolling(ROLLING_Z_WINDOW, min_periods=ROLLING_Z_MIN_PERIODS).mean().loc[last_i]), 4),
                "rolling_std_60": round(float(raw.rolling(ROLLING_Z_WINDOW, min_periods=ROLLING_Z_MIN_PERIODS).std().loc[last_i]), 4),
                "z_score": round(float(z.loc[last_i]), 4),
            }
        )

    channel_series: dict[str, pd.Series] = {}
    channel_detail: dict[str, Any] = {}
    for ch, frames in channel_frames.items():
        if not frames:
            continue
        channel_series[ch] = _inverse_variance_combine(frames)
        inv_w = _inverse_variance_weights(frames)
        last_i = channel_series[ch].last_valid_index()
        channel_detail[ch] = {
            "inverse_variance_weights": inv_w,
            "signal_ids": list(inv_w.keys()),
            "value": round(float(channel_series[ch].loc[last_i]), 4) if last_i is not None else None,
        }
        for s in signal_meta:
            if s["channel"] == ch and s["signal_id"] in inv_w:
                s["weight_in_channel"] = inv_w[s["signal_id"]]

    if not channel_series:
        raise ValueError("Insufficient history to decompose hybrid index.")

    weight_sum = sum(weights.get(ch, 0.0) for ch in channel_series) or 1.0
    channel_df = pd.DataFrame(channel_series)
    norm_ch_weights = {ch: round(weights.get(ch, 0.0) / weight_sum, 4) for ch in channel_series}

    def _weighted_row(row: pd.Series) -> float:
        mask = row.notna()
        if not mask.any():
            return float("nan")
        w = pd.Series({ch: norm_ch_weights[ch] for ch in channel_series})[mask]
        w = w / w.sum()
        return float(np.average(row[mask].astype(float), weights=w.values))

    composite_raw = channel_df.apply(_weighted_row, axis=1).dropna()
    last_idx = composite_raw.index[-1]
    composite_value = float(composite_raw.iloc[-1])
    smooth_series = composite_raw.rolling(COMPOSITE_SMOOTH_DAYS, min_periods=1).mean().dropna()
    smoothed_value = float(smooth_series.iloc[-1]) if len(smooth_series) else composite_value

    date_str = pd.Timestamp(panel.loc[last_idx, "date"]).strftime("%Y-%m-%d")
    contributions = {
        ch: round(norm_ch_weights[ch] * channel_detail[ch]["value"], 4)
        for ch in channel_detail
        if channel_detail[ch]["value"] is not None
    }

    interpretation = _build_interpretation(
        panel,
        composite_raw,
        smooth_series,
        signal_meta,
        channel_detail,
        norm_ch_weights,
        contributions,
        composite_value,
        smoothed_value,
        len(signal_meta),
    )

    return {
        "date": date_str,
        "parameters": {
            "rolling_window": ROLLING_Z_WINDOW,
            "rolling_min_periods": ROLLING_Z_MIN_PERIODS,
            "channel_weights": norm_ch_weights,
            "smooth_days": COMPOSITE_SMOOTH_DAYS,
        },
        "signals": signal_meta,
        "channels": channel_detail,
        "composite_raw": round(composite_value, 4),
        "composite_smoothed": round(smoothed_value, 4),
        "channel_contributions": contributions,
        "interpretation": interpretation,
        "formulas": {
            "z_score": "z_t(i) = (x_t(i) − μ_60(i)) / σ_60(i)",
            "channel": "Z_t(c) = Σ_i w_i(c) · z_t(i)   where w_i ∝ 1/Var(z(i))",
            "composite": "C_t = Σ_c α_c · Z_t(c)   (α: macro=0.50, market=0.42, news=0.08)",
            "smooth": f"C̃_t = (1/{COMPOSITE_SMOOTH_DAYS}) Σ_{'{k=0}'}^{'{8}'} C_{{t−k}}",
        },
    }


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
