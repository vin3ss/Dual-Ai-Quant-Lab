"""Execution layer — translate target weights into broker orders.

INTERFACE STUB. Implement against a broker API (Zerodha Kite / ICICI Breeze /
Fyers). Keep order generation separate from order routing so it can be unit-tested
without hitting a live account. Never auto-place live orders without an explicit,
human-confirmed switch.
"""
from __future__ import annotations
import pandas as pd


class ExecutionManager:
    def generate_orders(self, current_holdings: pd.Series,
                        target_weights: pd.Series, capital: float) -> pd.DataFrame:
        """Return a DataFrame of orders (ticker, side, qty) to move from current
        holdings to target. Pure function — no side effects."""
        raise NotImplementedError(
            "Compute target shares from weights*capital/price, diff vs current "
            "holdings, emit orders. Add lot-size rounding for F&O."
        )

    def route(self, orders: pd.DataFrame, *, live: bool = False):
        raise NotImplementedError(
            "Wire to broker API. Guard live=True behind explicit human confirmation."
        )
