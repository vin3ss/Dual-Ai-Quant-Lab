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


def test_deal_pressure_signs_net_buying():
    from nse_alpha_forge.analytics import deal_pressure
    idx = pd.date_range("2024-01-31", periods=2, freq="ME")
    cols = pd.Index(["AAA", "BBB"])
    deals = pd.DataFrame({
        "date": ["2024-01-10", "2024-01-12", "2024-02-05"],
        "symbol": ["AAA", "AAA", "BBB"],
        "action": ["BUY", "SELL", "BUY"],
        "quantity": [3000, 1000, 5000],
    })
    out = deal_pressure(deals, idx, cols)
    # AAA in Jan: net (3000-1000)/4000 = +0.5
    assert abs(out.loc[idx[0], "AAA"] - 0.5) < 1e-9
    # BBB in Feb: all buy -> +1.0
    assert out.loc[idx[1], "BBB"] == 1.0
    # no deals -> 0
    assert out.loc[idx[0], "BBB"] == 0.0


def test_delivery_accumulation_rises_with_delivery():
    from nse_alpha_forge.analytics import delivery_accumulation
    idx = pd.date_range("2023-01-31", periods=18, freq="ME")
    # delivery % low then rising in recent months
    vals = [30] * 14 + [60, 65, 70, 75]
    dp = pd.DataFrame({"AAA": vals}, index=idx)
    acc = delivery_accumulation(dp, lookback=3)
    assert acc.iloc[-1, 0] > 1.2  # recent delivery well above baseline


def test_smart_money_score_bounded():
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    prices = pd.DataFrame({"A": [100, 102, 101, 104, 103, 106, 108, 110]}, index=dates)
    vol = pd.DataFrame({"A": [1000, 1200, 900, 3000, 1100, 1500, 1300, 4000]}, index=dates)
    s = smart_money_score(prices, vol)
    assert s.iloc[-1, 0] <= 1.5 and s.iloc[-1, 0] >= -1.5
