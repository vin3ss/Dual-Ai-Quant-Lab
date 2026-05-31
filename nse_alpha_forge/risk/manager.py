"""Risk overlay: position/sector caps + volatility targeting.

Applied AFTER portfolio construction, BEFORE execution. All scaling uses only
trailing (point-in-time) information.
"""

from __future__ import annotations
import pandas as pd
import numpy as np

from ..config import RiskConfig


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def apply_caps(self, weights: pd.DataFrame, sectors: pd.Series) -> pd.DataFrame:
        w = weights.clip(upper=self.cfg.max_weight_per_name,
                         lower=-self.cfg.max_weight_per_name)
        # sector caps (scale down offending sector pro-rata)
        for dt, row in w.iterrows():
            sec_exp = row.groupby(sectors.reindex(row.index)).sum()
            for sec, exp in sec_exp.items():
                if abs(exp) > self.cfg.max_weight_per_sector and exp != 0:
                    scale = self.cfg.max_weight_per_sector / abs(exp)
                    members = sectors.index[sectors == sec]
                    w.loc[dt, w.columns.intersection(members)] *= scale
        return w

    def vol_target(self, weights: pd.DataFrame, returns: pd.DataFrame,
                   lookback: int = 12) -> pd.DataFrame:
        """Scale gross exposure so trailing realized portfolio vol ~ target."""
        port_ret = (weights.shift(1) * returns).sum(axis=1)
        realized = port_ret.rolling(lookback).std() * np.sqrt(self.cfg.trading_days / 21)
        scale = (self.cfg.target_annual_vol / realized).clip(upper=1.5).fillna(1.0)
        return weights.mul(scale, axis=0)

    def drawdown_derisk(self, weights: pd.DataFrame,
                        equity_curve: pd.Series) -> pd.DataFrame:
        """Cut exposure linearly once drawdown exceeds the trigger."""
        running_max = equity_curve.cummax()
        dd = 1 - equity_curve / running_max
        mult = (1 - (dd - self.cfg.drawdown_derisk_trigger).clip(lower=0) /
                (1 - self.cfg.drawdown_derisk_trigger)).clip(lower=0.0, upper=1.0)
        return weights.mul(mult.reindex(weights.index).fillna(1.0), axis=0)
