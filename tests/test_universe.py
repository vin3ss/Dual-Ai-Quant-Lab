import numpy as np
import pandas as pd

from nse_alpha_forge.portfolio.universe import liquid_universe_mask, apply_liquidity_filter


def _data():
    dates = pd.date_range("2022-01-31", periods=12, freq="ME")
    tickers = [f"S{i}" for i in range(10)]
    prices = pd.DataFrame(100.0, index=dates, columns=tickers)
    # S0..S9 with increasing volume -> S9 most liquid
    volume = pd.DataFrame(
        {t: [1000 * (i + 1)] * 12 for i, t in enumerate(tickers)}, index=dates
    )
    return prices, volume


def test_mask_keeps_top_n():
    prices, volume = _data()
    mask = liquid_universe_mask(prices, volume, top_n=3, lookback=3)
    last = mask.iloc[-1]
    assert last.sum() == 3
    # the 3 highest-volume names are S7, S8, S9
    assert set(last[last].index) == {"S7", "S8", "S9"}


def test_mask_is_point_in_time():
    prices, volume = _data()
    base = liquid_universe_mask(prices, volume, top_n=3, lookback=3)

    shocked_vol = volume.copy()
    k = 8
    shocked_vol.iloc[k:, 0] = 10_000_000  # make S0 hugely liquid in the future
    shocked = liquid_universe_mask(prices, shocked_vol, top_n=3, lookback=3)

    # past eligibility must be unchanged by a future liquidity shock
    pd.testing.assert_frame_equal(base.iloc[:k], shocked.iloc[:k])


def test_apply_filter_blanks_illiquid():
    prices, volume = _data()
    signal = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
    out = apply_liquidity_filter(signal, prices, volume, top_n=3, lookback=3)
    last = out.iloc[-1]
    assert last.notna().sum() == 3
    assert last[["S7", "S8", "S9"]].notna().all()
    assert last[["S0", "S1"]].isna().all()


def test_no_volume_is_noop():
    prices, _ = _data()
    signal = pd.DataFrame(1.0, index=prices.index, columns=prices.columns)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = apply_liquidity_filter(signal, prices, None, top_n=3)
    assert out.notna().all().all()
