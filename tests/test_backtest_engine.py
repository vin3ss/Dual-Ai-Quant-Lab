import pandas as pd

from nse_alpha_forge.config import Config
from nse_alpha_forge.backtest.engine import Backtester


def _zero_cost(cfg: Config) -> None:
    c = cfg.cost
    c.brokerage = c.stt_buy = c.stt_sell = c.exchange_txn = c.sebi_turnover = 0.0
    c.gst = c.stamp_duty_buy = c.stamp_duty_sell = 0.0
    c.base_impact_bps = c.impact_coefficient_bps = 0.0
    c.risk_free_annual = 0.0  # isolate execution behavior from cash yield


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


def test_idle_cash_earns_risk_free_return_on_flat_market():
    import pytest

    dates = pd.date_range("2024-01-31", periods=4, freq="ME")
    returns = pd.DataFrame({"AAA": [0.0, 0.0, 0.0, 0.0]}, index=dates)
    weights = pd.DataFrame({"AAA": [0.5, 0.5, 0.5, 0.5]}, index=dates)   # 50% invested
    prices = pd.DataFrame({"AAA": [100.0] * 4}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000_000.0] * 4}, index=dates)

    cfg = Config()
    cfg.cost.execution_lag_bars = 0
    cfg.cost.risk_free_annual = 0.06
    _zero_cost(cfg)
    cfg.cost.risk_free_annual = 0.06  # re-set after _zero_cost zeroed it

    result = Backtester(cfg).run(weights=weights, returns=returns,
                                 prices=prices, volume=volume)

    expected = 0.5 * (0.06 / 12)   # 50% idle * monthly rf
    assert result.returns.iloc[1] == pytest.approx(expected)
    assert result.returns.iloc[2] == pytest.approx(expected)
    assert result.stats["avg_idle_cash"] > 0.0


def test_sharpe_is_excess_over_risk_free():
    """A higher risk-free rate must LOWER Sharpe (excess measurement), so idle-cash
    yield can't masquerade as skill."""
    dates = pd.date_range("2020-01-31", periods=24, freq="ME")
    pattern = [0.01, 0.00, 0.02, 0.01, 0.00, 0.02]
    returns = pd.DataFrame({"AAA": (pattern * 4)}, index=dates)
    weights = pd.DataFrame({"AAA": [1.0] * 24}, index=dates)   # fully invested, no idle cash
    prices = pd.DataFrame({"AAA": [100.0] * 24}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000_000.0] * 24}, index=dates)

    lo = Config(); lo.cost.execution_lag_bars = 0; _zero_cost(lo)          # rf=0
    hi = Config(); hi.cost.execution_lag_bars = 0; _zero_cost(hi); hi.cost.risk_free_annual = 0.06

    s_lo = Backtester(lo).run(weights, returns, prices=prices, volume=volume).stats["sharpe"]
    s_hi = Backtester(hi).run(weights, returns, prices=prices, volume=volume).stats["sharpe"]

    assert s_hi < s_lo
