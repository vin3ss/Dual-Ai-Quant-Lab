"""Quality factor — high ROE, low accruals, stable earnings.

Quality-Momentum is the top long-horizon performer in NSE backtests.

CRITICAL anti-leakage requirement: fundamentals MUST be lagged to their actual
filing/availability date, never the fiscal period-end date. `data.fundamentals`
is expected to already be point-in-time (indexed by availability date).
"""

from __future__ import annotations
import pandas as pd

from ..base import AlphaSignal


class QualitySignal(AlphaSignal):
    name = "quality"

    def __init__(self, weights: dict | None = None):
        # equal-weight composite of the three sub-signals by default
        self.weights = weights or {"roe": 1 / 3, "neg_accruals": 1 / 3,
                                   "earnings_stability": 1 / 3}

    def compute(self, data) -> pd.DataFrame:
        f = data.fundamentals  # dict of point-in-time DataFrames (date x ticker)

        roe = f["roe"]
        # lower accruals = higher quality, so negate
        neg_accruals = -f["accruals"]
        # earnings stability = inverse of trailing earnings volatility
        earnings_stability = -f["earnings_vol"]

        composite = (
            self.weights["roe"] * self.zscore(roe)
            + self.weights["neg_accruals"] * self.zscore(neg_accruals)
            + self.weights["earnings_stability"] * self.zscore(earnings_stability)
        )
        return self.winsorize(self.zscore(composite))
