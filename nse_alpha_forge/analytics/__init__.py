"""Decision-support analytics (monitoring, not alpha).

Smart-money / money-flow proxies for a live intelligence screen — NOT validated alpha
and NOT part of the backtest. Surfaces information for a human to judge.
"""
from .smart_money import (
    volume_spike, money_flow, smart_money_score,
    delivery_accumulation, deal_pressure,
)

__all__ = ["volume_spike", "money_flow", "smart_money_score",
           "delivery_accumulation", "deal_pressure"]
