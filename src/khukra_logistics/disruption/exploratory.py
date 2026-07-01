"""Advanced exploratory analysis over disruption signal panels."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from khukra_logistics.disruption.bayesian import (
    bayesian_correlation,
    bayesian_model_compare_nested,
)
from khukra_logistics.disruption.hybrid_composite import SPARSE_SIGNALS
from khukra_logistics.disruption.statistics import _returns, composite_risk_index


def _signal_cols(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c != "date"]


def _prepare_explore_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Make sparse signals merge-safe: no news day = zero stress, not missing."""
    work = panel.copy()
    for col in SPARSE_SIGNALS:
        if col in work.columns:
            work[col] = work[col].fillna(0.0)
    return work


def _level_cols(panel: pd.DataFrame, min_coverage: float = 0.15) -> list[str]:
    """Signals with enough observations for level-based analysis (incl. zero-filled news)."""
    n = max(len(panel), 1)
    return [c for c in _signal_cols(panel) if panel[c].notna().sum() / n >= min_coverage]


def _return_cols(panel: pd.DataFrame, min_obs: int = 80) -> list[str]:
    """Signals with enough return history — excludes sparse count-based series like news."""
    cols: list[str] = []
    for col in _signal_cols(panel):
        if col in SPARSE_SIGNALS:
            continue
        if panel[col].notna().sum() < min_obs:
            continue
        cols.append(col)
    return cols


def _aligned_returns(panel: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    ret = pd.DataFrame({"date": panel["date"]})
    for col in cols:
        ret[col] = _returns(panel[col])
    return ret.dropna(subset=cols, how="any")


def correlation_matrices(panel: pd.DataFrame) -> dict[str, Any]:
    """Bayesian Pearson correlation with credible intervals on aligned levels."""
    panel = _prepare_explore_panel(panel)
    cols = _level_cols(panel)
    aligned = panel[["date", *cols]].dropna()
    if len(aligned) < 30:
        raise ValueError("Need at least 30 aligned observations for correlation matrices.")

    pearson_cells: list[dict[str, Any]] = []
    for a in cols:
        for b in cols:
            if a == b:
                post = {"r": 1.0, "ci_low": 1.0, "ci_high": 1.0, "prob_positive": 1.0}
            else:
                post = bayesian_correlation(aligned[a].values, aligned[b].values)
            pearson_cells.append(
                {
                    "signal_a": a,
                    "signal_b": b,
                    "value": round(post["r"], 4),
                    "ci_low": round(post["ci_low"], 4),
                    "ci_high": round(post["ci_high"], 4),
                    "prob_positive": round(post["prob_positive"], 4),
                }
            )

    return {
        "signals": cols,
        "n_obs": int(len(aligned)),
        "pearson": pearson_cells,
        "interpretation": (
            "Bayesian posterior for pairwise Pearson r (Fisher-z prior). "
            "Cells show r with 95% credible intervals; colour intensity uses posterior mean."
        ),
    }


def mutual_information_matrix(panel: pd.DataFrame, bins: int = 12) -> dict[str, Any]:
    """Pairwise mutual information from histogram binning (captures non-linear dependence)."""
    panel = _prepare_explore_panel(panel)
    cols = _level_cols(panel)
    aligned = panel[cols].dropna()
    if len(aligned) < 40:
        raise ValueError("Need at least 40 observations for mutual information.")

    def _mi(x: np.ndarray, y: np.ndarray) -> float:
        c_xy, _, _ = np.histogram2d(x, y, bins=bins)
        p_xy = c_xy / c_xy.sum()
        p_x = p_xy.sum(axis=1)
        p_y = p_xy.sum(axis=0)
        nz = p_xy > 0
        mi = float(np.sum(p_xy[nz] * np.log(p_xy[nz] / (p_x[:, None] * p_y[None, :])[nz])))
        return mi

    cells: list[dict[str, Any]] = []
    for i, a in enumerate(cols):
        for b in cols[i:]:
            mi = _mi(aligned[a].values, aligned[b].values)
            cells.append({"signal_a": a, "signal_b": b, "mutual_information": round(mi, 4)})

    top = max(cells, key=lambda c: c["mutual_information"] if c["signal_a"] != c["signal_b"] else -1)
    return {
        "signals": cols,
        "bins": bins,
        "cells": cells,
        "interpretation": (
            f"Highest non-linear dependence: {top['signal_a']} ↔ {top['signal_b']} "
            f"(MI={top['mutual_information']:.3f}). MI complements Pearson by catching non-linear links."
        ),
    }


def pca_exploration(panel: pd.DataFrame, n_components: int = 3) -> dict[str, Any]:
    """PCA on standardized signal levels — latent disruption factors."""
    panel = _prepare_explore_panel(panel)
    cols = _level_cols(panel)
    aligned = panel[cols].dropna()
    if len(aligned) < 40 or len(cols) < 2:
        raise ValueError("Need ≥40 rows and ≥2 signals for PCA.")

    n_components = min(n_components, len(cols))
    x = aligned[cols].values
    x_std = (x - x.mean(axis=0)) / x.std(axis=0, ddof=1)
    x_std = np.nan_to_num(x_std, nan=0.0)

    cov = np.cov(x_std, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    explained = eigvals / eigvals.sum()
    loadings = eigvecs[:, :n_components]
    scores = x_std @ loadings

    dates = panel.loc[aligned.index, "date"].dt.strftime("%Y-%m-%d").tolist()
    components: list[dict[str, Any]] = []
    for i in range(n_components):
        components.append(
            {
                "component": f"PC{i + 1}",
                "explained_variance": round(float(explained[i]), 4),
                "explained_pct": round(float(explained[i] * 100), 2),
                "loadings": {
                    cols[j]: round(float(loadings[j, i]), 4) for j in range(len(cols))
                },
                "series": {
                    "dates": dates,
                    "values": [round(float(v), 6) for v in scores[:, i]],
                },
            }
        )

    return {
        "n_components": n_components,
        "components": components,
        "interpretation": (
            f"PC1 explains {components[0]['explained_pct']:.1f}% of cross-signal variance — "
            "a latent 'common disruption factor'. Inspect loadings to see which proxies drive it."
        ),
    }


def rolling_correlation(
    panel: pd.DataFrame,
    window: int = 60,
    max_pairs: int = 3,
) -> dict[str, Any]:
    """Rolling Pearson correlation on returns for the strongest static pairs."""
    panel = _prepare_explore_panel(panel)
    cols = _return_cols(panel)
    ret = _aligned_returns(panel, cols)
    if len(ret) < window + 10:
        raise ValueError(f"Need at least {window + 10} return observations for rolling correlation.")

    static_corr: list[tuple[str, str, float]] = []
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r, _ = stats.pearsonr(ret[a], ret[b])
            static_corr.append((a, b, float(r)))
    static_corr.sort(key=lambda t: abs(t[2]), reverse=True)
    targets = static_corr[:max_pairs]

    series_list: list[dict[str, Any]] = []
    for a, b, static_r in targets:
        roll = ret[a].rolling(window).corr(ret[b])
        clean = roll.dropna()
        series_list.append(
            {
                "signal_a": a,
                "signal_b": b,
                "static_pearson_r": round(static_r, 4),
                "window_days": window,
                "series": {
                    "dates": ret.loc[clean.index, "date"].dt.strftime("%Y-%m-%d").tolist(),
                    "correlation": [round(float(v), 4) for v in clean.tolist()],
                },
            }
        )

    return {
        "window_days": window,
        "pairs": series_list,
        "interpretation": (
            f"Rolling {window}-day return correlation for the {len(series_list)} strongest static pairs. "
            "Regime shifts show up as correlation breakdowns or spikes."
        ),
    }


def _segment_changepoints(values: np.ndarray, min_seg: int = 40, max_breaks: int = 5) -> list[int]:
    """Binary segmentation on mean shifts (simple changepoint detection)."""
    n = len(values)
    if n < 2 * min_seg:
        return []

    breakpoints: list[int] = []

    def _best_split(start: int, end: int) -> tuple[int, float]:
        best_idx = -1
        best_gain = 0.0
        segment = values[start:end]
        if len(segment) < 2 * min_seg:
            return -1, 0.0
        total_var = float(np.var(segment))
        if total_var == 0:
            return -1, 0.0
        for idx in range(start + min_seg, end - min_seg + 1):
            left = values[start:idx]
            right = values[idx:end]
            gain = total_var - (
                len(left) * np.var(left) + len(right) * np.var(right)
            ) / len(segment)
            if gain > best_gain:
                best_gain = gain
                best_idx = idx
        return best_idx, best_gain

    def _recurse(start: int, end: int, depth: int) -> None:
        if depth >= max_breaks:
            return
        idx, gain = _best_split(start, end)
        if idx < 0 or gain < 1e-6:
            return
        breakpoints.append(idx)
        _recurse(start, idx, depth + 1)
        _recurse(idx, end, depth + 1)

    _recurse(0, n, 0)
    return sorted(set(breakpoints))


def changepoint_detection(panel: pd.DataFrame, max_breaks: int = 5) -> dict[str, Any]:
    """Detect mean-shift changepoints on composite z-index and per-signal z-scores."""
    panel = _prepare_explore_panel(panel)
    composite = composite_risk_index(panel)
    z = np.array(composite["series"]["composite_z"], dtype=float)
    dates = composite["series"]["dates"]
    composite_bps = _segment_changepoints(z, max_breaks=max_breaks)

    per_signal: list[dict[str, Any]] = []
    for col in _signal_cols(panel):
        s = panel[col].dropna()
        if len(s) < 80:
            continue
        roll_mean = s.rolling(60, min_periods=20).mean()
        roll_std = s.rolling(60, min_periods=20).std().replace(0, np.nan)
        z_s = ((s - roll_mean) / roll_std).dropna()
        if len(z_s) < 80:
            continue
        idxs = _segment_changepoints(z_s.values, min_seg=30, max_breaks=3)
        if not idxs:
            continue
        signal_dates = panel.loc[z_s.index, "date"].dt.strftime("%Y-%m-%d").tolist()
        per_signal.append(
            {
                "signal_id": col,
                "changepoints": [
                    {"date": signal_dates[i], "index": i} for i in idxs if i < len(signal_dates)
                ],
            }
        )

    return {
        "composite": {
            "changepoints": [
                {"date": dates[i], "index": i, "composite_z": round(float(z[i]), 4)}
                for i in composite_bps
                if i < len(dates)
            ],
        },
        "per_signal": per_signal,
        "interpretation": (
            f"Detected {len(composite_bps)} composite regime break(s) via binary segmentation on "
            "variance reduction. Marks where multi-signal stress structurally shifted."
        ),
    }


def _clustering_cols(aligned: pd.DataFrame, cols: list[str]) -> list[str]:
    """Drop near-constant series — they produce NaN correlations and break linkage."""
    usable = [c for c in cols if float(aligned[c].std(ddof=1)) > 1e-8]
    if len(usable) >= 2:
        return usable
    ranked = sorted(cols, key=lambda c: float(aligned[c].std(ddof=1)), reverse=True)
    return ranked[: max(2, min(len(ranked), len(cols)))]


def signal_clustering(panel: pd.DataFrame) -> dict[str, Any]:
    """Hierarchical clustering of signals by correlation distance."""
    panel = _prepare_explore_panel(panel)
    cols = _level_cols(panel)
    aligned = panel[cols].dropna()
    if len(aligned) < 30 or len(cols) < 2:
        raise ValueError("Need ≥30 rows and ≥2 signals for clustering.")

    cluster_cols = _clustering_cols(aligned, cols)
    corr = aligned[cluster_cols].corr().values
    corr = np.clip(np.nan_to_num(corr, nan=0.0), -1.0, 1.0)
    dist = 1.0 - np.abs(corr)
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)
    z = linkage(condensed, method="average")
    labels = fcluster(z, t=0.55, criterion="distance")

    clusters: dict[int, list[str]] = {}
    for col, label in zip(cluster_cols, labels):
        clusters.setdefault(int(label), []).append(col)

    excluded = [c for c in cols if c not in cluster_cols]
    note = ""
    if excluded:
        note = f" Excluded low-variance signals from clustering: {', '.join(excluded)}."

    return {
        "signals": cluster_cols,
        "excluded_signals": excluded,
        "linkage": [
            {"left": int(row[0]), "right": int(row[1]), "distance": round(float(row[2]), 4)}
            for row in z
        ],
        "clusters": [
            {"cluster_id": k, "signals": sorted(v)} for k, v in sorted(clusters.items())
        ],
        "interpretation": (
            "Signals clustered by |correlation| distance. Tight clusters co-move and may "
            "represent redundant disruption channels; distant signals add independent information."
            + note
        ),
    }


def bayesian_predictive_screen(panel: pd.DataFrame, max_lag: int = 5, top_n: int = 5) -> dict[str, Any]:
    """Bayesian model comparison: does signal x improve predictive density for y?"""
    panel = _prepare_explore_panel(panel)
    cols = _return_cols(panel)
    ret = _aligned_returns(panel, cols)
    if len(ret) < max_lag + 40:
        raise ValueError("Insufficient return history for predictive screening.")

    results: list[dict[str, Any]] = []

    for cause in cols:
        for effect in cols:
            if cause == effect:
                continue
            df = pd.DataFrame({"y": ret[effect], "x": ret[cause]})
            for lag in range(1, max_lag + 1):
                df[f"y_l{lag}"] = df["y"].shift(lag)
                df[f"x_l{lag}"] = df["x"].shift(lag)
            df = df.dropna()
            if len(df) < max_lag + 25:
                continue
            y_v = df["y"].values
            y_cols = [f"y_l{lag}" for lag in range(1, max_lag + 1)]
            x_cols = [f"x_l{lag}" for lag in range(1, max_lag + 1)]
            X_r = np.column_stack([np.ones(len(df)), df[y_cols].values])
            X_f = np.column_stack([np.ones(len(df)), df[y_cols].values, df[x_cols].values])
            cmp = bayesian_model_compare_nested(y_v, X_r, X_f)
            if cmp["posterior_predictive_prob"] < 0.6:
                continue
            results.append(
                {
                    "cause": cause,
                    "effect": effect,
                    "posterior_prob": round(cmp["posterior_predictive_prob"], 4),
                    "log_bayes_factor": round(cmp["log_bayes_factor"], 4),
                    "interpretation": (
                        f"{cause} improves predictive density for {effect} "
                        f"(P(M_full|data)={cmp['posterior_predictive_prob']:.0%}, "
                        f"log BF={cmp['log_bayes_factor']:.2f})."
                    ),
                }
            )

    results.sort(key=lambda r: r["posterior_prob"], reverse=True)
    return {
        "max_lag": max_lag,
        "tests": results[:top_n],
        "interpretation": (
            "Bayesian model comparison (BIC approximation) asking whether lags of one signal "
            "improve out-of-sample predictive density for another — replaces frequentist Granger F-tests."
        ),
    }


def run_advanced_exploration(panel: pd.DataFrame) -> dict[str, Any]:
    """Run full advanced exploratory suite on aligned panel."""
    methods: list[str] = []
    out: dict[str, Any] = {}

    for name, fn in [
        ("correlation_matrices", correlation_matrices),
        ("mutual_information", mutual_information_matrix),
        ("pca", lambda p: pca_exploration(p, n_components=3)),
        ("rolling_correlation", rolling_correlation),
        ("changepoints", changepoint_detection),
        ("clustering", signal_clustering),
        ("bayesian_predictive", bayesian_predictive_screen),
    ]:
        try:
            out[name] = fn(panel)
            methods.append(name)
        except ValueError:
            out[name] = None

    return {
        "methods_run": methods,
        "methodology": (
            "Bayesian exploration: correlation posteriors with credible intervals, MI, PCA factors, "
            "rolling correlation, changepoint segmentation, clustering, and predictive model comparison."
        ),
        **out,
    }
