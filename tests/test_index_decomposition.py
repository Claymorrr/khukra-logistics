"""Tests for hybrid index mathematical decomposition."""

from __future__ import annotations

import numpy as np
import pandas as pd

from khukra.disruption.hybrid_composite import decompose_hybrid_index


def test_decompose_hybrid_index_returns_formula_fields():
    rng = np.random.default_rng(1)
    n = 200
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    trend = np.linspace(0, 2, n)
    panel = pd.DataFrame(
        {
            "date": dates,
            "vix": 20 + trend * 3 + rng.normal(0, 0.3, n),
            "oil_wti": 70 + trend * 5 + rng.normal(0, 0.3, n),
            "shipping_basket": 15 + trend * 2 + rng.normal(0, 0.3, n),
            "eurusd": 1.1 + rng.normal(0, 0.01, n),
        }
    )
    result = decompose_hybrid_index(panel)
    assert "formulas" in result
    assert "composite_raw" in result
    assert "composite_smoothed" in result
    assert len(result["signals"]) >= 3
    assert "macro" in result["channels"] or "market" in result["channels"]
    contrib_sum = sum(result["channel_contributions"].values())
    assert abs(contrib_sum - result["composite_raw"]) < 0.05
    assert "interpretation" in result
    assert result["interpretation"]["regime"] in ("calm", "neutral", "watch", "elevated")
    assert len(result["interpretation"]["top_drivers"]) >= 1
    assert "headline" in result["interpretation"]
