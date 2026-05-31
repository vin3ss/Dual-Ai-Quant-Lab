import pandas as pd
import pytest

from nse_alpha_forge.alpha.macro import MacroSignal, MacroDataWarning
from nse_alpha_forge.data import MarketData, make_synthetic_data


def _macro_fixture():
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    prices = pd.DataFrame(
        {
            "BANK1": [100, 101, 102, 103, 104, 105, 106, 107],
            "AUTO1": [100, 100, 101, 102, 103, 104, 105, 106],
            "FMCG1": [200, 199, 198, 197, 196, 195, 194, 193],
            "PHARMA1": [150, 151, 150, 151, 150, 151, 150, 151],
            "METAL1": [80, 81, 82, 83, 84, 85, 86, 87],
        },
        index=dates,
    )
    sectors = pd.Series(
        {
            "BANK1": "BANK",
            "AUTO1": "AUTO",
            "FMCG1": "FMCG",
            "PHARMA1": "PHARMA",
            "METAL1": "METAL",
        },
        name="sector",
    )
    macro = pd.DataFrame(
        {
            "repo_rate": [6.50, 6.50, 6.25, 6.25, 6.00, 6.00, 5.75, 5.75],
            "cpi": [6.0, 5.8, 5.6, 5.4, 5.2, 5.1, 4.9, 4.8],
            "iip": [2.0, 2.1, 2.2, 2.5, 2.8, 3.0, 3.2, 3.4],
        },
        index=dates,
    )
    return MarketData(prices=prices, sectors=sectors, macro=macro)


def test_macro_neutral_when_absent():
    data = make_synthetic_data(n_tickers=8, n_months=24, seed=11)

    with pytest.warns(MacroDataWarning, match="data.macro is absent"):
        out = MacroSignal().compute(data)

    assert out.shape == data.prices.shape
    assert (out == 0.0).all().all()


def test_macro_output_bounded():
    data = _macro_fixture()
    out = MacroSignal().compute(data)

    assert out.index.equals(data.prices.index)
    assert out.columns.equals(data.prices.columns)
    assert out.max().max() <= 1.0
    assert out.min().min() >= -1.0
    assert out.notna().all().all()


def test_macro_point_in_time_future_shock_does_not_change_past():
    base_data = _macro_fixture()
    shocked_data = _macro_fixture()

    k = 5
    shocked_data.macro.iloc[k:] = shocked_data.macro.iloc[k:] * 100.0

    base = MacroSignal().compute(base_data)
    shocked = MacroSignal().compute(shocked_data)

    pd.testing.assert_frame_equal(base.iloc[:k], shocked.iloc[:k])


def test_falling_rates_tilt_rate_sensitive_over_defensives():
    data = _macro_fixture()
    out = MacroSignal().compute(data)

    last = out.iloc[-1]

    rate_sensitive = last[["BANK1", "AUTO1"]].mean()
    defensive = last[["FMCG1", "PHARMA1"]].mean()
    unrelated = last["METAL1"]

    assert rate_sensitive > defensive
    assert unrelated == 0.0
