import pandas as pd

from nse_alpha_forge.config import Config
from nse_alpha_forge.backtest.engine import Backtester


def _zero_cost(cfg: Config) -> None:
    c = cfg.cost
    c.brokerage = c.stt_buy = c.stt_sell = c.exchange_txn = c.sebi_turnover = 0.0
    c.gst = c.stamp_duty_buy = c.stamp_duty_sell = 0.0
    c.base_impact_bps = c.impact_coefficient_bps = 0.0


def test_execution_lag_prevents_signal_from_earning_next_bar_return():
    dates = pd.date_range("2024-01-31", periods=4, freq="ME")

    returns = pd.DataFrame({"AAA": [0.0, 0.0, 0.50, 0.10]}, index=dates)
    # Signal/weight becomes known only at close of dates[1].
    weights = pd.DataFrame({"AAA": [0.0, 1.0, 1.0, 1.0]}, index=dates)
    prices = pd.DataFrame({"AAA": [100.0, 100.0, 150.0, 165.0]}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000_000.0] * 4}, index=dates)

    cfg = Config()
    cfg.cost.execution_lag_bars = 1
    _zero_cost(cfg)

    result = Backtester(cfg).run(weights=weights, returns=returns,
                                 prices=prices, volume=volume)

    # The 50% close[1]->close[2] jump is not earnable: position decided at close[1]
    # fills next bar.
    assert result.returns.loc[dates[2]] == 0.0
    # It starts earning only after the extra execution lag.
    assert result.returns.loc[dates[3]] == 0.10


def test_execution_lag_zero_is_legacy_behavior():
    dates = pd.date_range("2024-01-31", periods=4, freq="ME")
    returns = pd.DataFrame({"AAA": [0.0, 0.0, 0.50, 0.10]}, index=dates)
    weights = pd.DataFrame({"AAA": [0.0, 1.0, 1.0, 1.0]}, index=dates)
    prices = pd.DataFrame({"AAA": [100.0, 100.0, 150.0, 165.0]}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000_000.0] * 4}, index=dates)

    cfg = Config()  # execution_lag_bars defaults to 0
    _zero_cost(cfg)

    result = Backtester(cfg).run(weights=weights, returns=returns,
                                 prices=prices, volume=volume)

    # Legacy: weight known at close[1] earns the close[1]->close[2] +50% (the look-ahead
    # this issue is about). Confirms default behavior is unchanged by the patch.
    assert result.returns.loc[dates[2]] == 0.50
