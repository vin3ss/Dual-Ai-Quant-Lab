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

    def apply_regime(self, weights: pd.DataFrame,
                     multiplier: pd.Series) -> pd.DataFrame:
        """Scale exposure by a point-in-time regime multiplier in [0, 1].

        Consistent with the other overlays: deterministic, vectorized, and never
        amplifies (multiplier is capped at 1, so no hidden leverage). The
        multiplier is assumed already point-in-time (see RegimeDetector).
        """
        if not isinstance(multiplier, pd.Series):
            raise TypeError("multiplier must be a pandas Series")

        aligned = multiplier.reindex(weights.index).ffill().fillna(1.0)

        if ((aligned < 0) | (aligned > 1)).any():
            raise ValueError("regime multiplier must lie in [0, 1]")

        return weights.mul(aligned, axis=0)

    def capacity_aware_targets(
        self,
        target_weights: pd.DataFrame,
        prices: pd.DataFrame,
        volume: pd.DataFrame,
        portfolio_value: float,
        max_adv_participation: float,
        candidate_scores: pd.DataFrame | None = None,
        adv_window: int = 20,
        max_passes: int = 5,
    ) -> pd.DataFrame:
        """Resize target weights so rebalance trades respect ADV capacity (#15).

        Long-only path: clip each name's rebalance delta to its trailing-ADV trade
        capacity, then redistribute clipped BUY capital to the next eligible names
        by score so intentional gross exposure is preserved when the universe can
        absorb it. Cash is left only when the whole universe is capacity-bound.
        Point-in-time: ADV at t uses history through t-1 only.
        """
        if prices is None or volume is None:
            return target_weights
        if portfolio_value <= 0:
            raise ValueError("portfolio_value must be > 0")
        if max_adv_participation <= 0:
            raise ValueError("max_adv_participation must be > 0")

        weights = target_weights.reindex(columns=prices.columns).fillna(0.0).copy()
        prices = prices.reindex_like(weights).astype(float)
        volume = volume.reindex_like(weights).astype(float)

        dollar_volume = prices * volume
        adv = (dollar_volume.rolling(adv_window, min_periods=max(1, adv_window // 3))
               .mean().shift(1))

        max_trade_weight = (adv * max_adv_participation / portfolio_value) \
            .replace([np.inf, -np.inf], np.nan).fillna(0.0)

        if candidate_scores is not None:
            scores = candidate_scores.reindex_like(weights).fillna(-np.inf)
        else:
            scores = weights.where(weights > 0, -np.inf)

        out = pd.DataFrame(0.0, index=weights.index, columns=weights.columns)
        prev = pd.Series(0.0, index=weights.columns)

        for dt in weights.index:
            desired = weights.loc[dt].clip(lower=0.0)
            cap = max_trade_weight.loc[dt].clip(lower=0.0)
            score = scores.loc[dt]

            delta = desired - prev
            clipped_delta = delta.clip(lower=-cap, upper=cap)
            current = (prev + clipped_delta).clip(lower=0.0)

            target_gross = desired.abs().sum()
            missing = max(target_gross - current.abs().sum(), 0.0)

            for _ in range(max_passes):
                if missing <= 1e-12:
                    break
                remaining_buy_cap = (prev + cap - current).clip(lower=0.0)
                eligible = remaining_buy_cap[
                    (remaining_buy_cap > 1e-12)
                    & score.replace([np.inf, -np.inf], np.nan).notna()
                ]
                if eligible.empty:
                    break
                order = score.loc[eligible.index].sort_values(ascending=False).index
                allocated = 0.0
                for name in order:
                    add = min(missing - allocated, remaining_buy_cap.loc[name])
                    if add <= 0:
                        continue
                    current.loc[name] += add
                    allocated += add
                    if allocated >= missing - 1e-12:
                        break
                if allocated <= 1e-12:
                    break
                missing -= allocated

            out.loc[dt] = current
            prev = current

        return out
