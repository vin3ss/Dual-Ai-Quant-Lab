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
from .costs import transaction_costs


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    turnover: pd.Series
    stats: dict
    cost_breakdown: object | None = None

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

    def run(
        self,
        weights: pd.DataFrame,
        returns: pd.DataFrame,
        prices: pd.DataFrame | None = None,
        volume: pd.DataFrame | None = None,
    ) -> BacktestResult:
        weights = weights.reindex(columns=returns.columns).fillna(0.0)

        desired_delta = weights.diff().fillna(weights)
        clipped_delta, costs = transaction_costs(
            delta_weights=desired_delta,
            cost=self.cfg.cost,
            prices=prices,
            volume=volume,
            portfolio_value=self.cfg.cost.portfolio_value,
            clip_to_capacity=True,
        )

        # Reconstruct the actually-executable weight path after capacity clipping.
        executable_weights = clipped_delta.cumsum().reindex_like(weights).fillna(0.0)

        execution_lag = int(getattr(self.cfg.cost, "execution_lag_bars", 0))
        if execution_lag < 0:
            raise ValueError("execution_lag_bars must be >= 0")

        # Base shift(1): weights decided at date t are not applied to return indexed t.
        # Extra execution_lag_bars:
        #   0 = legacy close(t) fill / earn close(t)->close(t+1)
        #   1 = next-bar fill / earn only after that next bar (no same-close look-ahead)
        applied_exec = executable_weights.shift(1 + execution_lag).fillna(0.0)

        target_exposure = weights.abs().sum(axis=1)
        executed_exposure = executable_weights.abs().sum(axis=1)
        invested = applied_exec.abs().sum(axis=1).clip(lower=0.0)
        idle_cash = (1.0 - invested).clip(lower=0.0)

        ppy = self._infer_ppy(returns.index)
        rf_annual = float(getattr(self.cfg.cost, "risk_free_annual", 0.0))
        rf_period = rf_annual / ppy

        gross_ret = (applied_exec * returns).sum(axis=1)
        cash_ret = idle_cash * rf_period

        turnover = clipped_delta.abs().sum(axis=1).shift(execution_lag).fillna(0.0)
        cost_drag = costs.total.shift(execution_lag).reindex(gross_ret.index).fillna(0.0)

        net_ret = gross_ret + cash_ret - cost_drag
        equity = (1 + net_ret).cumprod()

        stats = self._stats(net_ret, equity, turnover)
        stats["avg_invested"] = invested.mean()
        stats["avg_idle_cash"] = idle_cash.mean()
        stats["rf_period"] = rf_period
        stats["avg_target_exposure"] = target_exposure.mean()
        stats["avg_executed_exposure"] = executed_exposure.mean()
        stats["avg_applied_exposure"] = invested.mean()
        stats["avg_exposure_gap"] = (
            target_exposure.reindex(executed_exposure.index).fillna(0.0)
            - executed_exposure
        ).mean()
        stats["avg_explicit_cost"] = costs.explicit.mean()
        stats["avg_impact_cost"] = costs.impact.mean()
        stats["capacity_clips"] = (
            int(costs.clipped_trades.sum().sum())
            if costs.clipped_trades is not None
            else 0
        )

        return BacktestResult(equity, net_ret, turnover, stats, costs)

    def _stats(self, ret: pd.Series, equity: pd.Series,
               turnover: pd.Series) -> dict:
        periods_per_year = self._infer_ppy(ret.index)
        n = len(ret)
        ann_factor = periods_per_year
        cagr = equity.iloc[-1] ** (ann_factor / max(n, 1)) - 1 if n else 0.0
        vol = ret.std() * np.sqrt(ann_factor)
        # Sharpe on EXCESS-over-risk-free returns, so idle-cash yield (#17) cannot
        # masquerade as skill. A 100%-cash book has ~0 excess Sharpe.
        rf_period = float(getattr(self.cfg.cost, "risk_free_annual", 0.0)) / periods_per_year
        sharpe = ((ret.mean() - rf_period) * ann_factor) / vol if vol else 0.0
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
