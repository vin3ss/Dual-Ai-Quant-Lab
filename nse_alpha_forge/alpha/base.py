"""Base class and helpers shared by all alpha signals."""

from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class AlphaSignal(ABC):
    """A cross-sectional alpha signal.

    Convention: `compute` returns a DataFrame indexed by date, columns = tickers,
    values = the raw signal. Higher means more attractive (long). The portfolio
    layer handles standardization and neutralization, but signals may pre-standardize.
    """

    name: str = "base"

    @abstractmethod
    def compute(self, data: "MarketData") -> pd.DataFrame:  # noqa: F821
        ...

    # --- shared utilities -------------------------------------------------
    @staticmethod
    def zscore(df: pd.DataFrame) -> pd.DataFrame:
        """Cross-sectional z-score per date (row-wise)."""
        mu = df.mean(axis=1)
        sd = df.std(axis=1).replace(0, np.nan)
        return df.sub(mu, axis=0).div(sd, axis=0)

    @staticmethod
    def sector_neutralize(signal: pd.DataFrame, sectors: pd.Series) -> pd.DataFrame:
        """Demean the signal within each sector, per date.

        `sectors` maps ticker -> sector. Removes unintended sector tilts.
        """
        out = signal.copy()
        for dt, row in signal.iterrows():
            grp = row.groupby(sectors.reindex(row.index))
            out.loc[dt] = row - grp.transform("mean")
        return out

    @staticmethod
    def winsorize(df: pd.DataFrame, limits: float = 0.02) -> pd.DataFrame:
        lo = df.quantile(limits, axis=1)
        hi = df.quantile(1 - limits, axis=1)
        return df.clip(lower=lo, upper=hi, axis=0)
