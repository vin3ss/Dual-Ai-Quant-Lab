"""Central configuration. Keep all tunable knobs here so backtests are reproducible."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CostModel:
    """Round-trip Indian equity transaction costs, in fraction of traded value.

    These are illustrative defaults — calibrate to your broker and segment.
    """
    brokerage: float = 0.0003        # 0.03% (discount broker, capped in practice)
    stt: float = 0.001               # securities transaction tax (delivery sell side)
    exchange_txn: float = 0.0000325  # NSE transaction charge
    gst: float = 0.18                # GST on (brokerage + exchange charges)
    stamp_duty: float = 0.00015      # buy side
    # Impact cost is size-dependent; modeled separately in backtest.costs
    base_impact_bps: float = 5.0     # bps of additional slippage at low participation


@dataclass
class RiskConfig:
    target_annual_vol: float = 0.12  # portfolio vol target
    max_weight_per_name: float = 0.05
    max_weight_per_sector: float = 0.25
    max_gross_exposure: float = 1.0  # long-only by default
    drawdown_derisk_trigger: float = 0.15   # start cutting risk past 15% DD
    trading_days: int = 252


@dataclass
class StrategyConfig:
    universe: str = "NIFTY500"
    rebalance: str = "M"             # 'M' monthly, 'Q' quarterly, 'W' weekly
    momentum_lookback_months: int = 12
    momentum_skip_months: int = 1    # skip most recent month (reversal)
    quantiles: int = 5               # long top quantile
    sector_neutral: bool = True
    long_only: bool = True


@dataclass
class Config:
    cost: CostModel = field(default_factory=CostModel)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)


DEFAULT = Config()
