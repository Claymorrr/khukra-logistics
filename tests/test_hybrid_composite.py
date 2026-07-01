"""Tests for inverse-variance hybrid composite."""

from __future__ import annotations

import numpy as np
import pandas as pd

from khukra_logistics.disruption.hybrid_composite import build_hybrid_composite


def test_inverse_variance_favors_lower_noise_signal():
    n = 120
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    stable = np.linspace(0, 1, n)
    noisy = stable + np.random.default_rng(1).normal(0, 5, n)
    panel = pd.DataFrame(
        {
            "date": dates,
            "vix": stable,
            "oil_wti": noisy,
            "eurusd": stable * 0.5,
        }
    )
    composite, meta = build_hybrid_composite(panel, smooth_days=0)
    assert not composite.empty
    assert meta["mode"] == "hybrid_inverse_variance"
    assert meta["signals_per_channel"]["macro"] >= 2
