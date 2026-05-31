"""Regime detection — gate or scale exposure by market state.

Returns a per-date risk multiplier in [0, 1].

Point-in-time rule:
At timestamp t, the multiplier uses only information available strictly before t
via `.shift(1)`. This avoids same-bar / same-close look-ahead leakage.
"""

from __future__ import annotations

import warnings
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
        trend_off_multiplier: float = 0.60,
        high_vol_multiplier: float = 0.70,
        extreme_vol_multiplier: float = 0.40,
        warmup_multiplier: float = 0.50,
        vix_high_percentile: float = 0.80,
        vix_extreme_percentile: float = 0.95,
        vix_high_multiplier: float = 0.75,
        vix_extreme_multiplier: float = 0.50,
        fii_mild_z: float = -1.0,
        fii_extreme_z: float = -2.0,
        fii_mild_multiplier: float = 0.85,
        fii_extreme_multiplier: float = 0.65,
        bars_per_year: int = 12,
        use_equal_weight_index: bool = True,
    ):
        self.fast_trend_window = fast_trend_window
        self.slow_trend_window = slow_trend_window
        self.vol_window = vol_window
        self.vol_percentile_window = vol_percentile_window
        self.high_vol_percentile = high_vol_percentile
        self.extreme_vol_percentile = extreme_vol_percentile
        self.trend_off_multiplier = trend_off_multiplier
        self.high_vol_multiplier = high_vol_multiplier
        self.extreme_vol_multiplier = extreme_vol_multiplier
        self.warmup_multiplier = warmup_multiplier
        self.vix_high_percentile = vix_high_percentile
        self.vix_extreme_percentile = vix_extreme_percentile
        self.vix_high_multiplier = vix_high_multiplier
        self.vix_extreme_multiplier = vix_extreme_multiplier
        self.fii_mild_z = fii_mild_z
        self.fii_extreme_z = fii_extreme_z
        self.fii_mild_multiplier = fii_mild_multiplier
        self.fii_extreme_multiplier = fii_extreme_multiplier
        self.bars_per_year = bars_per_year
        self.use_equal_weight_index = use_equal_weight_index

    def detect(self, data) -> pd.Series:
        """Return per-date risk multiplier in [0, 1].

        Expected:
            data.prices: date x ticker adjusted close prices.

        Optional:
            data.macro["nifty_close"] / "NIFTY_CLOSE"
            data.macro["india_vix"] / "INDIA_VIX"
            data.macro["fii_net"] / "FII_NET"
        """
        prices = self._validate_prices(data.prices)
        index = self._get_market_index(data, prices)

        index_lagged = index.shift(1)
        returns = index_lagged.pct_change()

        fast_ma = index_lagged.rolling(
            self.fast_trend_window,
            min_periods=self.fast_trend_window,
        ).mean()

        slow_ma = index_lagged.rolling(
            self.slow_trend_window,
            min_periods=self.slow_trend_window,
        ).mean()

        trend_gate = pd.Series(self.trend_off_multiplier, index=prices.index, dtype=float)
        trend_gate.loc[fast_ma > slow_ma] = 1.0

        realized_vol = returns.rolling(
            self.vol_window,
            min_periods=self.vol_window,
        ).std()

        vol_min_periods = max(self.vol_window, self.vol_percentile_window // 3)

        high_vol_threshold = realized_vol.rolling(
            self.vol_percentile_window,
            min_periods=vol_min_periods,
        ).quantile(self.high_vol_percentile)

        extreme_vol_threshold = realized_vol.rolling(
            self.vol_percentile_window,
            min_periods=vol_min_periods,
        ).quantile(self.extreme_vol_percentile)

        vol_gate = pd.Series(1.0, index=prices.index, dtype=float)
        vol_gate.loc[realized_vol > high_vol_threshold] = self.high_vol_multiplier
        vol_gate.loc[realized_vol > extreme_vol_threshold] = self.extreme_vol_multiplier

        macro_gate = self._macro_gate(data, prices.index)

        multiplier = (trend_gate * vol_gate * macro_gate).clip(0.0, 1.0)

        warmup = max(
            self.slow_trend_window,
            self.vol_window + self.vol_percentile_window // 3,
        )
        multiplier.iloc[:warmup] = self.warmup_multiplier

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
            macro = macro.sort_index()
            for col in ("nifty_close", "NIFTY_CLOSE", "nifty", "NIFTY", "benchmark_close"):
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
                "No benchmark index found in data.macro and equal-weight fallback is disabled."
            )

        warnings.warn(
            "Using equal-weight universe proxy for regime detection. "
            "This can introduce survivorship bias if data.prices contains only surviving tickers. "
            "Use only for synthetic/demo data unless constituents are point-in-time.",
            RuntimeWarning,
            stacklevel=2,
        )

        returns = prices.pct_change()
        proxy = (1.0 + returns.mean(axis=1, skipna=True).fillna(0.0)).cumprod()
        return proxy.rename("market_index")

    def _macro_gate(self, data, index: pd.DatetimeIndex) -> pd.Series:
        macro = getattr(data, "macro", None)
        gate = pd.Series(1.0, index=index, dtype=float)

        if not isinstance(macro, pd.DataFrame) or macro.empty:
            return gate

        macro = macro.sort_index().reindex(index).ffill()

        vix_col = self._first_existing_col(
            macro,
            ("india_vix", "INDIA_VIX", "vix", "VIX"),
        )
        if vix_col:
            vix = macro[vix_col].astype(float).shift(1)

            vix_window = self.bars_per_year
            vix_min_periods = max(3, self.bars_per_year // 4)

            vix_pct = vix.rolling(
                vix_window,
                min_periods=vix_min_periods,
            ).rank(pct=True)

            gate.loc[vix_pct > self.vix_high_percentile] *= self.vix_high_multiplier
            gate.loc[vix_pct > self.vix_extreme_percentile] *= self.vix_extreme_multiplier

        fii_col = self._first_existing_col(
            macro,
            ("fii_net", "FII_NET", "fii_cash_net", "FII_CASH_NET"),
        )
        if fii_col:
            fii = macro[fii_col].astype(float).shift(1)

            fii_window = max(3, self.bars_per_year // 2)
            fii_min_periods = max(3, fii_window // 3)

            fii_mean = fii.rolling(fii_window, min_periods=fii_min_periods).mean()
            fii_std = fii.rolling(fii_window, min_periods=fii_min_periods).std()
            fii_z = (fii - fii_mean) / fii_std.replace(0, np.nan)

            gate.loc[fii_z < self.fii_mild_z] *= self.fii_mild_multiplier
            gate.loc[fii_z < self.fii_extreme_z] *= self.fii_extreme_multiplier

        return gate.clip(0.0, 1.0)

    @staticmethod
    def _first_existing_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None
