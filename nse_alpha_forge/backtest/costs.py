"""Indian equity transaction-cost model.

Round-trip cost as a fraction of traded notional, plus a size-dependent impact
term. Deliberately conservative — under-modeling costs is a top reason Indian
backtests look better than reality.
"""

from __future__ import annotations
from ..config import CostModel


def round_trip_cost(cost: CostModel, participation: float = 0.0) -> float:
    """Per-unit-turnover cost (one side). Multiply by per-period turnover.

    participation: fraction of ADV traded; drives nonlinear impact.
    """
    explicit = (
        cost.brokerage
        + cost.exchange_txn
        + cost.stamp_duty
    )
    explicit *= (1 + cost.gst)          # GST on brokerage + exchange charges
    explicit += cost.stt                # STT
    impact = (cost.base_impact_bps / 1e4) * (1 + 3 * participation)
    return explicit + impact
