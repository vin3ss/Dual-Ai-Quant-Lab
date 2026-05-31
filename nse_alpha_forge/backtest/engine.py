"""Vectorized cross-sectional backtest engine.

Critical anti-leakage rule: weights decided at date t are applied to returns
realized over (t, t+1]. We shift weights forward by one period before multiplying
by returns. Costs are charged on turnover at each rebalance.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import numpy as np

from ..config import Config
from .costs import round_trip_cost


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    turnover: pd.Series
    stats: dict

    def summary(self) -> str:
        s = self.stats
        return (
            f"CAGR:        {s['cagr']:.2%}\n"
            f"Vol (ann):   {s['vol']:.2%}\n"
            f"Sharpe:      {s['sharpe']:.2f}\n"
            f"Max DD:      {s['max_dd']:.2%}\n"
            f"Avg turnover:{s['avg_turnover']:.2%}/rebal\n"
            f"Periods:     {s['n_periods']}"
        )


class Backtester:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def run(self, weights: pd.DataFrame, returns: pd.DataFrame) -> BacktestResult:
        weights = weights.reindex(columns=returns.columns).fillna(0.0)

        # weights at t applied to returns over next period -> shift(1)
        applied = weights.shift(1).fillna(0.0)
        gross_ret = (applied * returns).sum(axis=1)

        # turnover & costs charged at the period weights change
        turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
        per_unit_cost = round_trip_cost(self.cfg.cost)
        cost_drag = turnover * per_unit_cost

        net_ret = gross_ret - cost_drag.reindex(gross_ret.index).fillna(0.0)
        equity = (1 + net_ret).cumprod()

        stats = self._stats(net_ret, equity, turnover)
        return BacktestResult(equity, net_ret, turnover, stats)

    def _stats(self, ret: pd.Series, equity: pd.Series,
               turnover: pd.Series) -> dict:
        periods_per_year = self._infer_ppy(ret.index)
        n = len(ret)
        ann_factor = periods_per_year
        cagr = equity.iloc[-1] ** (ann_factor / max(n, 1)) - 1 if n else 0.0
        vol = ret.std() * np.sqrt(ann_factor)
        sharpe = (ret.mean() * ann_factor) / vol if vol else 0.0
        dd = 1 - equity / equity.cummax()
        return {
            "cagr": cagr,
            "vol": vol,
            "sharpe": sharpe,
            "max_dd": dd.max(),
            "avg_turnover": turnover.mean(),
            "n_periods": n,
        }

    @staticmethod
    def _infer_ppy(idx: pd.Index) -> int:
        if len(idx) < 3:
            return 12
        med = pd.Series(idx).diff().median().days
        if med <= 9:
            return 52
        if med <= 45:
            return 12
        return 4
