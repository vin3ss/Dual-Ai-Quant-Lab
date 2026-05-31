"""Regime → risk integration tests.

Covers RiskManager.apply_regime (the wiring) plus two correctness properties the
critique demanded: (1) the gate actually reduces drawdown in a synthetic crash,
(2) the detector has no future leakage across ALL dates, not just the last bar.
"""

import numpy as np
import pandas as pd
import pytest

from nse_alpha_forge.config import RiskConfig
from nse_alpha_forge.risk import RiskManager
from nse_alpha_forge.data import MarketData, make_synthetic_data
from nse_alpha_forge.alpha.regime import RegimeDetector


def _rm():
    return RiskManager(RiskConfig())


def test_apply_regime_scales_weights():
    dates = pd.date_range("2025-01-31", periods=6, freq="ME")
    weights = pd.DataFrame(0.25, index=dates, columns=list("ABCD"))
    mult = pd.Series(0.5, index=dates)

    out = _rm().apply_regime(weights, mult)

    assert np.allclose(out.values, 0.125)
    assert out.index.equals(weights.index)


def test_apply_regime_rejects_out_of_range():
    dates = pd.date_range("2025-01-31", periods=4, freq="ME")
    weights = pd.DataFrame(0.25, index=dates, columns=list("ABCD"))

    with pytest.raises(ValueError):
        _rm().apply_regime(weights, pd.Series(1.5, index=dates))

    with pytest.raises(TypeError):
        _rm().apply_regime(weights, [0.5, 0.5, 0.5, 0.5])


def _crash_market() -> tuple[MarketData, pd.Series]:
    """40 months of calm uptrend, then 12 months of a volatile crash."""
    dates = pd.date_range("2015-01-31", periods=52, freq="ME")
    tickers = list("ABCDE")
    calm = 0.01 + np.zeros(40)
    crash = np.array([-0.12, -0.08, 0.04, -0.15, -0.10, 0.05,
                      -0.13, -0.07, 0.03, -0.09, -0.06, 0.02])
    mkt = np.concatenate([calm, crash])
    prices = pd.DataFrame(
        100 * np.cumprod(1 + mkt)[:, None].repeat(len(tickers), axis=1),
        index=dates, columns=tickers,
    )
    data = MarketData(prices=prices, sectors=pd.Series("X", index=tickers))
    return data, pd.Series(mkt, index=dates)


def test_regime_de_risks_in_crash():
    data, _ = _crash_market()
    regime = RegimeDetector().detect(data)

    calm_avg = regime.iloc[24:40].mean()   # post-warmup, pre-crash
    crash_avg = regime.iloc[40:].mean()

    assert crash_avg < calm_avg            # gate cuts exposure entering the crash
    assert crash_avg < 0.6                 # and materially so


def test_regime_reduces_crash_drawdown():
    data, ret = _crash_market()
    regime = RegimeDetector().detect(data)

    def max_dd(r: pd.Series) -> float:
        eq = (1 + r).cumprod()
        return (1 - eq / eq.cummax()).max()

    gated = ret * regime.shift(1).fillna(1.0)   # point-in-time application

    assert max_dd(gated) < max_dd(ret)


def test_regime_detector_no_future_leakage_all_dates():
    data = make_synthetic_data(n_tickers=20, n_months=80, seed=42)
    base = RegimeDetector().detect(data)

    shocked = make_synthetic_data(n_tickers=20, n_months=80, seed=42)
    k = 50
    shocked.prices.iloc[k:] *= 5.0          # shock everything from date k onward

    out = RegimeDetector().detect(shocked)

    # Every date strictly before the shock must be byte-identical.
    pd.testing.assert_series_equal(base.iloc[:k], out.iloc[:k])
