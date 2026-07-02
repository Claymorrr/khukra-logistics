"""Statistical reasoning and insight discovery over disruption signal panels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from khukra.disruption.bayesian import (
    bayesian_correlation,
    bayesian_linear_forecast,
    bayesian_regime_prob,
    composite_posterior,
)
from khukra.disruption.forecasting import (
    PRODUCTION_METHOD,
    forecast_horizon,
    get_production_method,
    get_production_predictor,
    get_production_smooth_days,
    score_methods_fast,
    select_best_method,
)
from khukra.disruption.hybrid_composite import COMPOSITE_SMOOTH_DAYS, SPARSE_SIGNALS, build_hybrid_composite
from khukra.simulation.primitives import forecast_holt_linear


def _returns(series: pd.Series) -> pd.Series:
    return series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def profile_panel(panel: pd.DataFrame) -> dict[str, Any]:
    """Descriptive statistics per signal."""
    profiles: list[dict[str, Any]] = []
    signal_cols = [c for c in panel.columns if c != "date"]
    for col in signal_cols:
        s = panel[col].dropna()
        if len(s) < 5:
            continue
        profiles.append(
            {
                "signal_id": col,
                "row_count": int(len(s)),
                "first_date": str(panel.loc[s.index[0], "date"].date()),
                "last_date": str(panel.loc[s.index[-1], "date"].date()),
                "mean": float(s.mean()),
                "std": float(s.std()),
                "min": float(s.min()),
                "max": float(s.max()),
                "missing_pct": float(panel[col].isna().mean() * 100),
            }
        )
    return {"signals": profiles, "total": len(profiles)}


def _correlation_insight(a: str, b: str, x: pd.Series, y: pd.Series) -> dict[str, Any] | None:
    aligned = pd.concat([x, y], axis=1).dropna()
    if len(aligned) < 30:
        return None
    post = bayesian_correlation(aligned.iloc[:, 0].values, aligned.iloc[:, 1].values)
    r = post["r"]
    strength = "weak"
    if abs(r) >= 0.5:
        strength = "strong"
    elif abs(r) >= 0.3:
        strength = "moderate"
    direction = "positive" if r > 0 else "negative"
    credible = (post["ci_low"] > 0) or (post["ci_high"] < 0)
    return {
        "type": "correlation",
        "signal_a": a,
        "signal_b": b,
        "pearson_r": round(r, 4),
        "ci_low": round(post["ci_low"], 4),
        "ci_high": round(post["ci_high"], 4),
        "prob_positive": round(post["prob_positive"], 4),
        "prob_strong": round(post["prob_strong"], 4),
        "n_obs": int(len(aligned)),
        "credible_nonzero": bool(credible),
        "strength": strength,
        "direction": direction,
        "interpretation": (
            f"{a} and {b} show {strength} {direction} co-movement "
            f"(r={r:.2f}, 95% credible interval [{post['ci_low']:.2f}, {post['ci_high']:.2f}]). "
            f"P(positive correlation | data)={post['prob_positive']:.0%}."
        ),
    }


def _regime_insight(signal_id: str, series: pd.Series, window: int = 60) -> dict[str, Any] | None:
    clean = series.dropna()
    if len(clean) < window + 10:
        return None
    roll_mean = clean.rolling(window).mean()
    roll_std = clean.rolling(window).std().replace(0, np.nan)
    z = (clean - roll_mean) / roll_std
    current_z = float(z.iloc[-1])
    if np.isnan(current_z):
        return None

    history = clean.iloc[-window:].values
    post = bayesian_regime_prob(float(clean.iloc[-1]), history)
    prob_elevated = post["prob_elevated"]
    prob_depressed = post["prob_depressed"]
    if prob_elevated < 0.75 and prob_depressed < 0.75:
        return None

    regime = "elevated" if prob_elevated >= prob_depressed else "depressed"
    prob_regime = max(prob_elevated, prob_depressed)
    return {
        "type": "regime_shift",
        "signal_id": signal_id,
        "window_days": window,
        "z_score": round(current_z, 3),
        "prob_elevated": round(prob_elevated, 4),
        "prob_depressed": round(prob_depressed, 4),
        "regime": regime,
        "interpretation": (
            f"{signal_id} is likely {regime} vs its {window}-day history "
            f"(z={current_z:.2f}, P({regime})={prob_regime:.0%})."
        ),
    }


def _lead_lag_insight(
    leader: str,
    follower: str,
    x: pd.Series,
    y: pd.Series,
    max_lag: int = 20,
) -> dict[str, Any] | None:
    rx = _returns(x)
    ry = _returns(y)
    aligned = pd.concat([rx, ry], axis=1).dropna()
    if len(aligned) < 40:
        return None
    best_lag = 0
    best_corr = -2.0
    best_post: dict[str, float] | None = None
    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            a = aligned.iloc[:, 0].iloc[:-lag]
            b = aligned.iloc[:, 1].iloc[lag:]
        elif lag < 0:
            a = aligned.iloc[:, 0].iloc[-lag:]
            b = aligned.iloc[:, 1].iloc[:lag]
        else:
            a = aligned.iloc[:, 0]
            b = aligned.iloc[:, 1]
        if len(a) < 30:
            continue
        post = bayesian_correlation(a.values, b.values)
        corr = post["r"]
        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag
            best_post = post
    if best_post is None or best_post["prob_strong"] < 0.5:
        return None
    if best_lag > 0:
        text = f"{leader} return changes tend to lead {follower} by {best_lag} day(s)."
    elif best_lag < 0:
        text = f"{follower} return changes tend to lead {leader} by {-best_lag} day(s)."
    else:
        text = f"{leader} and {follower} return changes are contemporaneous."
    return {
        "type": "lead_lag",
        "leader": leader if best_lag >= 0 else follower,
        "follower": follower if best_lag >= 0 else leader,
        "best_lag_days": int(best_lag),
        "correlation": round(best_corr, 4),
        "prob_strong": round(best_post["prob_strong"], 4),
        "ci_low": round(best_post["ci_low"], 4),
        "ci_high": round(best_post["ci_high"], 4),
        "interpretation": (
            f"{text} P(|r|>0.3 | data)={best_post['prob_strong']:.0%}, "
            f"95% CI [{best_post['ci_low']:.2f}, {best_post['ci_high']:.2f}]."
        ),
    }


def discover_insights(panel: pd.DataFrame, max_pairs: int = 15) -> dict[str, Any]:
    """Scan cached panel for Bayesian correlations, regimes, and lead-lag structure."""
    signal_cols = [c for c in panel.columns if c != "date"]
    work = panel.copy()
    for sparse in SPARSE_SIGNALS:
        if sparse in work.columns:
            work[sparse] = work[sparse].fillna(0.0)
    insights: list[dict[str, Any]] = []

    for col in signal_cols:
        regime = _regime_insight(col, work[col])
        if regime:
            insights.append(regime)

    pairs_checked = 0
    for i, a in enumerate(signal_cols):
        for b in signal_cols[i + 1 :]:
            if pairs_checked >= max_pairs:
                break
            pair = _correlation_insight(a, b, work[a], work[b])
            if pair and (pair["credible_nonzero"] or pair["prob_strong"] >= 0.7):
                insights.append(pair)
            lead_lag = _lead_lag_insight(a, b, work[a], work[b])
            if lead_lag:
                insights.append(lead_lag)
            pairs_checked += 1

    insights.sort(
        key=lambda x: abs(
            x.get("prob_strong", x.get("prob_elevated", x.get("pearson_r", x.get("correlation", 0))))
        ),
        reverse=True,
    )
    return {
        "insight_count": len(insights),
        "insights": insights,
        "methodology": (
            "Bayesian inference: Fisher-z correlation posteriors (95% credible intervals), "
            "regime probabilities P(elevated|data) with |z|≥1.5 threshold, and return lead-lag "
            "with posterior P(|r|>0.3)."
        ),
    }


def composite_risk_index(panel: pd.DataFrame) -> dict[str, Any]:
    """Weighted hybrid z-score composite (macro / market / news) with Bayesian posterior."""
    signal_cols = [c for c in panel.columns if c != "date"]
    if not signal_cols:
        raise ValueError("No cached signals available. Run refresh first.")

    clean, hybrid_meta = build_hybrid_composite(panel, signal_cols, smooth_days=0)
    if len(clean) < 30:
        raise ValueError("Insufficient history to compute composite risk index.")

    current = float(clean.iloc[-1])
    p90 = float(np.percentile(clean, 90))
    p10 = float(np.percentile(clean, 10))
    post = composite_posterior(
        current,
        sum(hybrid_meta.get("signals_per_channel", {}).values()) or 1,
        int(len(clean)),
    )

    return {
        "current": round(current, 4),
        "ci_low": round(post["ci_low"], 4),
        "ci_high": round(post["ci_high"], 4),
        "prob_elevated": round(post["prob_elevated"], 4),
        "p90": round(p90, 4),
        "p10": round(p10, 4),
        "percentile_rank": round(float(stats.percentileofscore(clean, current)), 2),
        "hybrid": hybrid_meta,
        "interpretation": (
            f"Hybrid disruption index at {current:.2f}σ "
            f"(95% credible interval [{post['ci_low']:.2f}, {post['ci_high']:.2f}]). "
            f"P(elevated >1.5σ | data)={post['prob_elevated']:.0%}. "
            f"Historical percentile {stats.percentileofscore(clean, current):.0f}."
        ),
        "series": {
            "dates": panel.loc[clean.index, "date"].dt.strftime("%Y-%m-%d").tolist(),
            "composite_z": [float(v) for v in clean.tolist()],
        },
    }


def _method_scores_for_forecast(y_fore: np.ndarray) -> tuple[str, dict[str, dict[str, float]]]:
    """Prefer today's cached daily evaluation; fall back to fast Holt/MR scoring."""
    from datetime import date

    from khukra.disruption.evaluation import latest_evaluation

    cached = latest_evaluation()
    if cached and cached.get("evaluation_date") == date.today().isoformat():
        wf = cached.get("walk_forward", {})
        methods = wf.get("methods", {})
        if methods:
            return wf.get("best_method", PRODUCTION_METHOD), methods

    scores = score_methods_fast(y_fore)
    best = min(scores, key=lambda k: scores[k]["walk_forward_mae"])
    return best, scores


def production_model_forecast(panel: pd.DataFrame, horizon: int = 30) -> dict[str, Any]:
    """Low-latency production model path for UI — no full evaluation or Bayesian sweep."""
    smooth_days = get_production_smooth_days()
    method = get_production_method()
    predict_fn = get_production_predictor()
    smooth, hybrid_meta = build_hybrid_composite(panel, smooth_days=smooth_days)
    if len(smooth) < 40:
        raise ValueError("Need at least 40 observations for production forecast.")

    y_fore = smooth.values
    proj = forecast_horizon(y_fore, horizon, predict_fn=predict_fn)
    prod_dates = panel.loc[smooth.index, "date"]
    production_series = {
        "dates": pd.to_datetime(prod_dates).dt.strftime("%Y-%m-%d").tolist(),
        "values": [float(v) for v in smooth.tolist()],
    }

    _, method_scores = _method_scores_for_forecast(y_fore)
    prod_mae = method_scores.get(method, {}).get("walk_forward_mae")

    return {
        "horizon_days": horizon,
        "production_method": method,
        "selected_method": method,
        "smooth_days": hybrid_meta.get("smooth_days", smooth_days),
        "hybrid_mode": hybrid_meta.get("mode"),
        "production_series": production_series,
        "method_scores": method_scores,
        "forecast_mae": prod_mae,
        "forecast": proj["forecast"],
        "forecast_lower": proj["forecast_lower"],
        "forecast_upper": proj["forecast_upper"],
        "interpretation": (
            f"Production {method} on {smooth_days}-day smoothed hybrid "
            f"(walk-forward MAE={prod_mae:.3f} when measured)." if prod_mae is not None
            else f"Production {method} on {smooth_days}-day smoothed hybrid."
        ),
    }


def forecast_composite(panel: pd.DataFrame, horizon: int = 30) -> dict[str, Any]:
    """Production method projected over horizon; scores from daily cache when available."""
    composite = composite_risk_index(panel)
    y = np.array(composite["series"]["composite_z"], dtype=float)
    if len(y) < 40:
        raise ValueError("Need at least 40 observations for forecast.")

    smooth_days = get_production_smooth_days()
    method = get_production_method()
    predict_fn = get_production_predictor()
    smooth, hybrid_meta = build_hybrid_composite(panel, smooth_days=smooth_days)
    y_fore = smooth.values if len(smooth) >= 40 else y

    best_method, method_scores = _method_scores_for_forecast(y_fore)
    proj = forecast_horizon(y_fore, horizon, predict_fn=predict_fn)

    prod_dates = panel.loc[smooth.index, "date"]
    production_series = {
        "dates": pd.to_datetime(prod_dates).dt.strftime("%Y-%m-%d").tolist(),
        "values": [float(v) for v in smooth.tolist()],
    }

    train_n = max(20, int(len(y) * 0.75))
    y_train = y[:train_n]
    y_hold = y[train_n:]
    hold_forecast, _, _ = forecast_holt_linear(y_train, len(y_hold))
    mae_holt = float(np.mean(np.abs(y_hold - hold_forecast[: len(y_hold)]))) if len(y_hold) else 0.0
    prod_mae = method_scores.get(method, {}).get("walk_forward_mae", 0.0)
    resid = np.diff(y_fore[-60:]) if len(y_fore) > 60 else np.diff(y_fore)
    rmse = float(np.std(resid)) if len(resid) else 0.15

    return {
        "horizon_days": horizon,
        "selected_method": method,
        "method_scores": method_scores,
        "forecast_mae": round(float(prod_mae), 4),
        "forecast_rmse": round(rmse, 4),
        "forecast_mae_holt": round(mae_holt, 4),
        "credible_level": 0.95,
        "forecast": proj["forecast"],
        "forecast_lower": proj["forecast_lower"],
        "forecast_upper": proj["forecast_upper"],
        "current_composite_z": composite["current"],
        "smooth_days": hybrid_meta.get("smooth_days", smooth_days),
        "production_series": production_series,
        "hybrid_mode": hybrid_meta.get("mode"),
        "channel_weights": composite.get("hybrid", {}).get("channel_weights", {}),
        "interpretation": (
            f"Hybrid composite forecast via {method} "
            f"(walk-forward MAE={prod_mae:.3f} on 2y tail; Holt holdout {mae_holt:.3f}). "
            f"Channel weights: {composite.get('hybrid', {}).get('channel_weights', {})}."
        ),
    }
