"""Indian equity transaction-cost, impact, and capacity model.

Default rates are for Indian cash equity delivery-style backtests.

Source/date notes to validate before live/published research:
- Brokerage: broker-specific; default 0.03% per side, commonly discount-broker style.
- STT: equity delivery 0.1% on buy and sell side. Source: Indian STT schedule,
  checked 2026-05-31.
- Exchange transaction charge: NSE cash-market charge varies by exchange/circular.
  Default here is 0.00325% per side; validate against current NSE charge sheet.
- SEBI turnover fee: default 0.0001% per side, i.e. ₹10 per crore.
- GST: 18% on brokerage + exchange txn + SEBI fee, not on STT/stamp duty.
- Stamp duty: delivery equity buy side 0.015%, sell side 0.

Backtest bias warning:
These defaults can still flatter results if spreads, auction impact, partial fills,
liquidity droughts, taxes on realised gains, and broker-specific slabs/caps are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd

from ..config import CostModel


class CostModelWarning(RuntimeWarning):
    """Warning for cost/capacity assumptions that can bias a backtest."""


@dataclass
class CostBreakdown:
    explicit: pd.Series
    impact: pd.Series
    total: pd.Series
    participation: pd.DataFrame | None = None
    clipped_trades: pd.DataFrame | None = None


def side_cost_rate(cost: CostModel, side: str) -> float:
    """Return one-sided explicit cost rate as fraction of traded value."""
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")

    brokerage = cost.brokerage
    exchange = cost.exchange_txn
    sebi = getattr(cost, "sebi_turnover", 0.000001)
    gst = cost.gst * (brokerage + exchange + sebi)

    stt = cost.stt_buy if side == "buy" else cost.stt_sell
    stamp = cost.stamp_duty_buy if side == "buy" else cost.stamp_duty_sell

    return brokerage + exchange + sebi + gst + stt + stamp


def explicit_trade_cost(
    delta_weights: pd.DataFrame,
    cost: CostModel,
) -> pd.Series:
    """Explicit one-sided costs on signed rebalance trades."""
    buys = delta_weights.clip(lower=0.0)
    sells = (-delta_weights.clip(upper=0.0))

    buy_cost = buys.sum(axis=1) * side_cost_rate(cost, "buy")
    sell_cost = sells.sum(axis=1) * side_cost_rate(cost, "sell")

    return (buy_cost + sell_cost).rename("explicit_cost")


def estimate_participation(
    delta_weights: pd.DataFrame,
    prices: pd.DataFrame | None,
    volume: pd.DataFrame | None,
    portfolio_value: float,
    adv_window: int,
) -> pd.DataFrame | None:
    """Estimate trade participation = traded notional / ADV notional.

    Uses trailing ADV shifted by one bar. At date t, capacity cannot use t volume.
    """
    if prices is None or volume is None:
        warnings.warn(
            "No prices/volume supplied to cost model. Impact and capacity checks "
            "are disabled, which can materially overstate performance.",
            CostModelWarning,
            stacklevel=2,
        )
        return None

    prices = prices.reindex_like(delta_weights).astype(float)
    volume = volume.reindex_like(delta_weights).astype(float)

    dollar_volume = prices * volume
    adv = dollar_volume.rolling(adv_window, min_periods=max(1, adv_window // 3)).mean().shift(1)

    traded_notional = delta_weights.abs() * portfolio_value
    participation = traded_notional / adv.replace(0.0, np.nan)

    return participation.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def impact_cost(
    delta_weights: pd.DataFrame,
    participation: pd.DataFrame | None,
    cost: CostModel,
) -> pd.Series:
    """Nonlinear market impact cost.

    impact_rate = base_impact + impact_coefficient * participation^impact_exponent

    Cost is charged on traded notional weight.
    """
    if participation is None:
        return pd.Series(0.0, index=delta_weights.index, name="impact_cost")

    base = cost.base_impact_bps / 1e4
    variable = cost.impact_coefficient_bps / 1e4 * (
        participation.clip(lower=0.0) ** cost.impact_exponent
    )

    rate = base + variable
    impact = (delta_weights.abs() * rate).sum(axis=1)

    return impact.rename("impact_cost")


def apply_capacity_cap(
    delta_weights: pd.DataFrame,
    participation: pd.DataFrame | None,
    max_participation: float,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Clip trades so no name exceeds max ADV participation.

    Returns clipped delta weights and a boolean DataFrame showing where clipping engaged.
    """
    if participation is None:
        return delta_weights, None

    if max_participation <= 0:
        raise ValueError("max_participation must be > 0")

    scale = (max_participation / participation.replace(0.0, np.nan)).clip(upper=1.0)
    scale = scale.replace([np.inf, -np.inf], np.nan).fillna(1.0)

    clipped = participation > max_participation
    clipped_delta = delta_weights * scale

    return clipped_delta, clipped


def transaction_costs(
    delta_weights: pd.DataFrame,
    cost: CostModel,
    prices: pd.DataFrame | None = None,
    volume: pd.DataFrame | None = None,
    portfolio_value: float = 1.0,
    clip_to_capacity: bool = True,
) -> tuple[pd.DataFrame, CostBreakdown]:
    """Apply capacity cap and compute itemized transaction costs."""
    participation = estimate_participation(
        delta_weights=delta_weights,
        prices=prices,
        volume=volume,
        portfolio_value=portfolio_value,
        adv_window=cost.adv_window,
    )

    clipped_delta = delta_weights
    clipped_flags = None

    if clip_to_capacity and participation is not None:
        clipped_delta, clipped_flags = apply_capacity_cap(
            delta_weights=delta_weights,
            participation=participation,
            max_participation=cost.max_adv_participation,
        )

        if clipped_flags.any().any():
            warnings.warn(
                "Capacity cap engaged: at least one rebalance exceeded max ADV "
                "participation and was clipped.",
                CostModelWarning,
                stacklevel=2,
            )

        participation = estimate_participation(
            delta_weights=clipped_delta,
            prices=prices,
            volume=volume,
            portfolio_value=portfolio_value,
            adv_window=cost.adv_window,
        )

    explicit = explicit_trade_cost(clipped_delta, cost)
    impact = impact_cost(clipped_delta, participation, cost)
    total = (explicit + impact).rename("total_cost")

    return clipped_delta, CostBreakdown(
        explicit=explicit,
        impact=impact,
        total=total,
        participation=participation,
        clipped_trades=clipped_flags,
    )


def round_trip_cost(cost: CostModel, participation: float = 0.0) -> float:
    """Backward-compatible scalar cost estimate.

    Kept for older tests/callers. Prefer `transaction_costs`.
    """
    one_way = 0.5 * (side_cost_rate(cost, "buy") + side_cost_rate(cost, "sell"))
    impact = (cost.base_impact_bps / 1e4) + (
        cost.impact_coefficient_bps / 1e4
    ) * (max(participation, 0.0) ** cost.impact_exponent)
    return one_way + impact
