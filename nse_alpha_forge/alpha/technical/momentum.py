"""Cross-sectional price momentum — the most robust factor in Indian equities.

Recipe (evidence-aligned, see Research/AlphaIdeas/indian_quant_research_review.md):
  - 12-month total return, skipping the most recent month (short-term reversal)
  - risk-adjusted by trailing volatility
  - sector-neutralized at the portfolio layer
"""

from __future__ import annotations
import pandas as pd
import numpy as np

from ..base import AlphaSignal


class MomentumSignal(AlphaSignal):
    name = "momentum"

    def __init__(self, lookback_months: int = 12, skip_months: int = 1,
                 risk_adjust: bool = True):
        self.lookback = lookback_months
        self.skip = skip_months
        self.risk_adjust = risk_adjust

    def compute(self, data) -> pd.DataFrame:
        """data.prices: monthly (or resampled) close prices, date x ticker."""
        px = data.prices
        # total return from t-lookback to t-skip  (all known at t)
        ret = px.shift(self.skip) / px.shift(self.lookback) - 1.0

        if self.risk_adjust:
            monthly_ret = px.pct_change()
            vol = monthly_ret.rolling(self.lookback).std().shift(self.skip)
            ret = ret / vol.replace(0, np.nan)

        return self.winsorize(self.zscore(ret))
