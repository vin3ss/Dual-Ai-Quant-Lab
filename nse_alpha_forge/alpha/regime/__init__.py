"""Regime detection — leading market-risk gate.

Returns a per-date risk multiplier in [0, 1].

Design:
- Drawdown-from-peak gate: cuts risk quickly once market proxy falls from peak.
- Short realized-vol shock gate: compares fast vol to longer baseline.
- Optional India VIX gate: compares VIX to long-run mean/z-score, not rolling rank.

Point-in-time:
At timestamp t, the multiplier uses only information available strictly before t
via `.shift(1)`. Same-bar close/VIX is never used.
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd


class RegimeDetector:
    name = "regime"

    def __init__(
        self,
        # drawdown gate
        dd_mild_threshold: float = 0.06,
        dd_severe_threshold: float = 0.10,
        dd_mild_multiplier: float = 0.65,
        dd_severe_multiplier: float = 0.35,
        # realized-vol shock gate
        short_vol_window: int = 3,
        baseline_vol_window: int = 12,
        vol_mild_ratio: float = 1.50,
        vol_severe_ratio: float = 2.25,
        vol_mild_multiplier: float = 0.75,
        vol_severe_multiplier: float = 0.50,
        # India VIX long-baseline gate
        vix_baseline_window: int = 36,
        vix_mild_z: float = 1.0,
        vix_severe_z: float = 2.0,
        vix_mild_multiplier: float = 0.75,
        vix_severe_multiplier: float = 0.50,
        # general
        warmup_multiplier: float = 1.0,
        min_periods: int = 3,
        use_equal_weight_index: bool = True,
    ):
        self.dd_mild_threshold = dd_mild_threshold
        self.dd_severe_threshold = dd_severe_threshold
        self.dd_mild_multiplier = dd_mild_multiplier
        self.dd_severe_multiplier = dd_severe_multiplier

        self.short_vol_window = short_vol_window
        self.baseline_vol_window = baseline_vol_window
        self.vol_mild_ratio = vol_mild_ratio
        self.vol_severe_ratio = vol_severe_ratio
        self.vol_mild_multiplier = vol_mild_multiplier
        self.vol_severe_multiplier = vol_severe_multiplier

        self.vix_baseline_window = vix_baseline_window
        self.vix_mild_z = vix_mild_z
        self.vix_severe_z = vix_severe_z
        self.vix_mild_multiplier = vix_mild_multiplier
        self.vix_severe_multiplier = vix_severe_multiplier

        self.warmup_multiplier = warmup_multiplier
        self.min_periods = min_periods
        self.use_equal_weight_index = use_equal_weight_index

    def detect(self, data) -> pd.Series:
        """Return per-date risk multiplier in [0, 1].

        Expected:
            data.prices: date x ticker adjusted close prices.

        Optional:
            data.macro["nifty_close"] / "NIFTY_CLOSE" / "benchmark_close"
            data.macro["india_vix"] / "INDIA_VIX" / "vix"
        """
        prices = self._validate_prices(data.prices)
        index = self._get_market_index(data, prices)

        # Strict point-in-time lag.
        index_lagged = index.shift(1)

        dd_gate = self._drawdown_gate(index_lagged, prices.index)
        vol_gate = self._vol_gate(index_lagged, prices.index)
        vix_gate = self._vix_gate(data, prices.index)

        multiplier = (dd_gate * vol_gate * vix_gate).clip(0.0, 1.0)
        multiplier = multiplier.fillna(self.warmup_multiplier).clip(0.0, 1.0)

        return multiplier.rename("regime_multiplier")

    def _drawdown_gate(self, index_lagged: pd.Series, index: pd.Index) -> pd.Series:
        peak = index_lagged.cummax()
        drawdown = 1.0 - index_lagged / peak.replace(0.0, np.nan)

        gate = pd.Series(1.0, index=index, dtype=float)
        gate.loc[drawdown >= self.dd_mild_threshold] = self.dd_mild_multiplier
        gate.loc[drawdown >= self.dd_severe_threshold] = self.dd_severe_multiplier

        return gate

    def _vol_gate(self, index_lagged: pd.Series, index: pd.Index) -> pd.Series:
        ret = index_lagged.pct_change()

        short_vol = ret.rolling(
            self.short_vol_window,
            min_periods=max(2, min(self.min_periods, self.short_vol_window)),
        ).std()

        baseline_vol = ret.rolling(
            self.baseline_vol_window,
            min_periods=max(self.min_periods, self.short_vol_window),
        ).std()

        ratio = short_vol / baseline_vol.replace(0.0, np.nan)

        gate = pd.Series(1.0, index=index, dtype=float)
        gate.loc[ratio >= self.vol_mild_ratio] = self.vol_mild_multiplier
        gate.loc[ratio >= self.vol_severe_ratio] = self.vol_severe_multiplier

        return gate

    def _vix_gate(self, data, index: pd.Index) -> pd.Series:
        macro = getattr(data, "macro", None)
        gate = pd.Series(1.0, index=index, dtype=float)

        if not isinstance(macro, pd.DataFrame) or macro.empty:
            return gate

        macro = macro.copy()
        macro.columns = [str(c).lower().strip() for c in macro.columns]
        macro = macro.sort_index().reindex(index).ffill()

        vix_col = self._first_existing_col(
            macro,
            ("india_vix", "vix", "india vix"),
        )
        if vix_col is None:
            return gate

        # Strict point-in-time lag: today's gate cannot use today's VIX close.
        vix = macro[vix_col].astype(float).shift(1)

        baseline_mean = vix.rolling(
            self.vix_baseline_window,
            min_periods=max(self.min_periods, self.vix_baseline_window // 3),
        ).mean()

        baseline_std = vix.rolling(
            self.vix_baseline_window,
            min_periods=max(self.min_periods, self.vix_baseline_window // 3),
        ).std()

        z = (vix - baseline_mean) / baseline_std.replace(0.0, np.nan)

        gate.loc[z >= self.vix_mild_z] = self.vix_mild_multiplier
        gate.loc[z >= self.vix_severe_z] = self.vix_severe_multiplier

        return gate

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
            macro = macro.copy()
            macro.columns = [str(c).lower().strip() for c in macro.columns]
            macro = macro.sort_index()

            for col in ("nifty_close", "nifty", "benchmark_close"):
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

    @staticmethod
    def _first_existing_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None
