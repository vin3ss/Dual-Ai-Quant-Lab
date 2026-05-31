"""Central configuration. Keep all tunable knobs here so backtests are reproducible."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CostModel:
    """Indian cash-equity cost model.

    All rates are fractions of traded notional.
    Defaults are research approximations; validate against broker/NSE/SEBI circulars
    before publishing/live use.
    """
    brokerage: float = 0.0003

    # Equity delivery STT: 0.1% on buy and sell.
    stt_buy: float = 0.001
    stt_sell: float = 0.001

    # NSE cash-market transaction charge approximation.
    exchange_txn: float = 0.0000325

    # SEBI turnover fee approximation: ₹10 / crore = 0.0001%.
    sebi_turnover: float = 0.000001

    # GST on brokerage + exchange + SEBI charges.
    gst: float = 0.18

    # Stamp duty: equity delivery buy side.
    stamp_duty_buy: float = 0.00015
    stamp_duty_sell: float = 0.0

    # Market impact / capacity.
    base_impact_bps: float = 2.0
    impact_coefficient_bps: float = 20.0
    impact_exponent: float = 1.5
    adv_window: int = 20
    max_adv_participation: float = 0.10

    # Notional capital used for capacity/ADV checks.
    portfolio_value: float = 1_000_000.0

    # Execution timing.
    # 0 preserves the historical engine behavior:
    # weights decided at close(t) are applied from close(t)->close(t+1).
    # 1 is stricter next-bar execution:
    # weights decided at close(t) fill at next bar and start earning after that.
    execution_lag_bars: int = 0


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
