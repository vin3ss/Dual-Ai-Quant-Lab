import pandas as pd

from nse_alpha_forge.analytics import volume_spike, money_flow, smart_money_score


def test_money_flow_positive_on_steady_up_moves():
    dates = pd.date_range("2024-01-31", periods=6, freq="ME")
    prices = pd.DataFrame({"A": [100, 102, 104, 106, 108, 110]}, index=dates)
    volume = pd.DataFrame({"A": [1000] * 6}, index=dates)
    mf = money_flow(prices, volume, lookback=3)
    assert mf.iloc[-1, 0] > 0.9  # all up-moves -> accumulation ~ +1


def test_money_flow_negative_on_down_moves():
    dates = pd.date_range("2024-01-31", periods=6, freq="ME")
    prices = pd.DataFrame({"A": [110, 108, 106, 104, 102, 100]}, index=dates)
    volume = pd.DataFrame({"A": [1000] * 6}, index=dates)
    mf = money_flow(prices, volume, lookback=3)
    assert mf.iloc[-1, 0] < -0.9


def test_volume_spike_flags_elevated():
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    prices = pd.DataFrame({"A": [100] * 8}, index=dates)
    vol = pd.DataFrame({"A": [1000, 1000, 1000, 1000, 1000, 1000, 1000, 5000]}, index=dates)
    vs = volume_spike(prices, vol, lookback=6)
    assert vs.iloc[-1, 0] > 3.0  # 5000 vs ~1000 median


def test_smart_money_score_bounded():
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    prices = pd.DataFrame({"A": [100, 102, 101, 104, 103, 106, 108, 110]}, index=dates)
    vol = pd.DataFrame({"A": [1000, 1200, 900, 3000, 1100, 1500, 1300, 4000]}, index=dates)
    s = smart_money_score(prices, vol)
    assert s.iloc[-1, 0] <= 1.5 and s.iloc[-1, 0] >= -1.5
