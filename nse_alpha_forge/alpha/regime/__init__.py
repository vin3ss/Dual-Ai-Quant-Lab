"""Regime detection — gate or scale exposure by market state.

Returns a per-date risk multiplier in [0, 1].

Point-in-time rule:
At timestamp t, the multiplier uses only information available strictly before t
via `.shift(1)`. This avoids same-bar / same-close look-ahead leakage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class RegimeDetector:
    name = "regime"

    def __init__(
        self,
        fast_trend_window: int = 6,
        slow_trend_window: int = 12,
        vol_window: int = 6,
        vol_percentile_window: int = 36,
        high_vol_percentile: float = 0.80,
        extreme_vol_percentile: float = 0.95,
        use_equal_weight_index: bool = True,
    ):
        self.fast_trend_window = fast_trend_window
        self.slow_trend_window = slow_trend_window
        self.vol_window = vol_window
        self.vol_percentile_window = vol_percentile_window
        self.high_vol_percentile = high_vol_percentile
        self.extreme_vol_percentile = extreme_vol_percentile
        self.use_equal_weight_index = use_equal_weight_index

    def detect(self, data) -> pd.Series:
        """Return per-date risk multiplier in [0, 1].

        Expected inputs:
            data.prices: date x ticker adjusted close prices.

        Optional:
            data.macro["nifty_close"] or data.macro["NIFTY_CLOSE"]
            data.macro["india_vix"] or data.macro["INDIA_VIX"]
            data.macro["fii_net"] or data.macro["FII_NET"]

        Fallback:
            If no index series is available, uses an equal-weight synthetic
            market index from the tradable universe.
        """
        prices = self._validate_prices(data.prices)
        index = self._get_market_index(data, prices)

        # Strictly lag market state. Signal for t cannot use t close.
        index_lagged = index.shift(1)

        returns = index_lagged.pct_change()

        fast_ma = index_lagged.rolling(
            self.fast_trend_window, min_periods=self.fast_trend_window
        ).mean()
        slow_ma = index_lagged.rolling(
            self.slow_trend_window, min_periods=self.slow_trend_window
        ).mean()

        trend_on = fast_ma > slow_ma
        trend_gate = pd.Series(0.60, index=prices.index, dtype=float)
        trend_gate.loc[trend_on] = 1.00

        realized_vol = returns.rolling(
            self.vol_window, min_periods=self.vol_window
        ).std()

        high_vol_threshold = realized_vol.rolling(
            self.vol_percentile_window,
            min_periods=max(self.vol_window, self.vol_percentile_window // 3),
        ).quantile(self.high_vol_percentile)

        extreme_vol_threshold = realized_vol.rolling(
            self.vol_percentile_window,
            min_periods=max(self.vol_window, self.vol_percentile_window // 3),
        ).quantile(self.extreme_vol_percentile)

        vol_gate = pd.Series(1.00, index=prices.index, dtype=float)
        vol_gate.loc[realized_vol > high_vol_threshold] = 0.70
        vol_gate.loc[realized_vol > extreme_vol_threshold] = 0.40

        macro_gate = self._macro_gate(data, prices.index)

        multiplier = trend_gate * vol_gate * macro_gate
        multiplier = multiplier.clip(lower=0.0, upper=1.0)

        # Conservative during warm-up periods where slow/vol windows are unavailable.
        warmup = max(
            self.slow_trend_window,
            self.vol_window + self.vol_percentile_window // 3,
        )
        multiplier.iloc[:warmup] = 0.50

        return multiplier.rename("regime_multiplier")

    def _validate_prices(self, prices: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(prices, pd.DataFrame):
            raise TypeError("data.prices must be a pandas DataFrame.")

        if prices.empty:
            raise ValueError("data.prices is empty.")

        if not isinstance(prices.index, pd.DatetimeIndex):
            raise TypeError("data.prices index must be a DatetimeIndex.")

        clean = prices.sort_index().astype(float)

        if clean.index.has_duplicates:
            raise ValueError("data.prices index contains duplicate dates.")

        return clean

    def _get_market_index(self, data, prices: pd.DataFrame) -> pd.Series:
        macro = getattr(data, "macro", None)

        if isinstance(macro, pd.DataFrame) and not macro.empty:
            for col in ("nifty_close", "NIFTY_CLOSE", "nifty", "NIFTY"):
                if col in macro.columns:
                    return (
                        macro[col]
                        .reindex(prices.index)
                        .ffill()
                        .astype(float)
                        .rename("market_index")
                    )

        if not self.use_equal_weight_index:
            raise ValueError(
                "No market index found in data.macro and equal-weight fallback is disabled."
            )

        normalized = prices.div(prices.iloc[0]).replace([np.inf, -np.inf], np.nan)
        return normalized.mean(axis=1, skipna=True).rename("market_index")

    def _macro_gate(self, data, index: pd.DatetimeIndex) -> pd.Series:
        macro = getattr(data, "macro", None)
        gate = pd.Series(1.0, index=index, dtype=float)

        if not isinstance(macro, pd.DataFrame) or macro.empty:
            return gate

        macro = macro.sort_index().reindex(index).ffill()

        vix_col = self._first_existing_col(macro, ("india_vix", "INDIA_VIX", "vix", "VIX"))
        if vix_col:
            # Lag VIX so today's gate does not use today's final VIX print.
            vix = macro[vix_col].astype(float).shift(1)
            vix_pct = vix.rolling(252, min_periods=60).rank(pct=True)

            gate.loc[vix_pct > 0.80] *= 0.75
            gate.loc[vix_pct > 0.95] *= 0.50

        fii_col = self._first_existing_col(macro, ("fii_net", "FII_NET", "fii_cash_net", "FII_CASH_NET"))
        if fii_col:
            # Negative institutional flow shock reduces exposure.
            fii = macro[fii_col].astype(float).shift(1)
            fii_z = (fii - fii.rolling(60, min_periods=20).mean()) / fii.rolling(
                60, min_periods=20
            ).std()

            gate.loc[fii_z < -1.0] *= 0.85
            gate.loc[fii_z < -2.0] *= 0.65

        return gate.clip(lower=0.0, upper=1.0)

    @staticmethod
    def _first_existing_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None
