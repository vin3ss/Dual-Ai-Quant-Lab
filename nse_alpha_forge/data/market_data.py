"""Market-data container + a synthetic generator for offline demos/tests.

For real data, populate MarketData from nsefin/nsepython (EOD bhavcopy, option
chain, FII/DII) or a broker API. Keep everything point-in-time.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
import numpy as np


@dataclass
class MarketData:
    prices: pd.DataFrame                         # date x ticker close (adjusted)
    sectors: pd.Series                           # ticker -> sector
    fundamentals: dict = field(default_factory=dict)   # point-in-time frames
    option_chain: pd.DataFrame | None = None
    fii_deriv: pd.DataFrame | None = None
    macro: pd.DataFrame | None = None
    news: pd.DataFrame | None = None

    def returns(self) -> pd.DataFrame:
        return self.prices.pct_change()


def make_synthetic_data(n_tickers: int = 40, n_months: int = 120,
                        seed: int = 7) -> MarketData:
    """Deterministic synthetic universe with a mild momentum + quality structure,
    so the demo backtest produces sensible (not real) numbers offline."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-31", periods=n_months, freq="ME")
    tickers = [f"STK{i:02d}" for i in range(n_tickers)]
    sectors = pd.Series(
        rng.choice(["IT", "BANK", "PHARMA", "AUTO", "FMCG"], size=n_tickers),
        index=tickers, name="sector",
    )

    # Latent quality score per name; drives a small persistent return premium.
    quality_latent = rng.normal(0, 1, n_tickers)
    drift = 0.004 + 0.004 * (quality_latent / 3)        # monthly drift
    shocks = rng.normal(0, 0.07, size=(n_months, n_tickers))
    monthly_ret = drift + shocks
    # add momentum autocorrelation
    for t in range(1, n_months):
        monthly_ret[t] += 0.15 * monthly_ret[t - 1]

    prices = pd.DataFrame(100 * np.cumprod(1 + monthly_ret, axis=0),
                          index=dates, columns=tickers)

    # Point-in-time fundamentals (already lagged for the demo)
    roe = pd.DataFrame(rng.normal(quality_latent, 0.5, size=(n_months, n_tickers)),
                       index=dates, columns=tickers)
    accruals = pd.DataFrame(rng.normal(-quality_latent * 0.3, 0.5,
                                       size=(n_months, n_tickers)),
                            index=dates, columns=tickers)
    earnings_vol = pd.DataFrame(
        np.abs(rng.normal(1 - quality_latent * 0.2, 0.3, size=(n_months, n_tickers))),
        index=dates, columns=tickers)

    return MarketData(
        prices=prices,
        sectors=sectors,
        fundamentals={"roe": roe, "accruals": accruals, "earnings_vol": earnings_vol},
    )
