import pandas as pd

from nse_alpha_forge.alpha.regime import RegimeDetector
from nse_alpha_forge.data import MarketData


def test_regime_cuts_within_one_to_two_bars_of_drawdown():
    dates = pd.date_range("2020-01-31", periods=12, freq="ME")

    # Peak at t=4, crash at t=5. Because detector is shift(1), gate should cut at t=6,
    # i.e. one scored bar after the drawdown becomes observable.
    market = [100, 104, 108, 112, 116, 100, 92, 94, 96, 98, 100, 102]
    prices = pd.DataFrame({"AAA": market, "BBB": market}, index=dates)
    sectors = pd.Series({"AAA": "IT", "BBB": "BANK"}, name="sector")

    data = MarketData(prices=prices, sectors=sectors)

    gate = RegimeDetector(
        dd_mild_threshold=0.05,
        dd_severe_threshold=0.10,
        dd_mild_multiplier=0.60,
        dd_severe_multiplier=0.30,
        short_vol_window=3,
        baseline_vol_window=6,
        use_equal_weight_index=True,
    ).detect(data)

    crash_idx = 5
    assert gate.iloc[crash_idx] == 1.0  # same-bar crash not used
    assert gate.iloc[crash_idx + 1] < 1.0
    assert gate.iloc[crash_idx + 2] <= gate.iloc[crash_idx + 1]


def test_regime_does_not_derisk_during_steady_uptrend():
    dates = pd.date_range("2020-01-31", periods=18, freq="ME")
    market = [100 + 3 * i for i in range(len(dates))]

    prices = pd.DataFrame({"AAA": market, "BBB": market}, index=dates)
    sectors = pd.Series({"AAA": "IT", "BBB": "BANK"}, name="sector")

    data = MarketData(prices=prices, sectors=sectors)

    gate = RegimeDetector(
        dd_mild_threshold=0.05,
        dd_severe_threshold=0.10,
        short_vol_window=3,
        baseline_vol_window=6,
        use_equal_weight_index=True,
    ).detect(data)

    assert (gate.dropna() == 1.0).all()
