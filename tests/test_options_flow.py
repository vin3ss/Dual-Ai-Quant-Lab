import numpy as np
import pandas as pd
import pytest

from nse_alpha_forge.data import MarketData, make_synthetic_data
from nse_alpha_forge.alpha.options import OptionsFlowSignal, OptionsDataWarning


def _data_with_pcr(seed: int = 0) -> MarketData:
    dates = pd.date_range("2020-01-31", periods=24, freq="ME")
    tickers = list("ABCDE")
    rng = np.random.default_rng(seed)
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.01, 0.05, size=(24, 5)), axis=0),
        index=dates, columns=tickers,
    )
    pcr = pd.DataFrame(rng.uniform(0.5, 1.8, size=(24, 5)), index=dates, columns=tickers)
    return MarketData(prices=prices, sectors=pd.Series("X", index=tickers),
                      option_chain=pcr)


def test_options_flow_bounded_and_no_nan():
    sig = OptionsFlowSignal().compute(_data_with_pcr())
    assert sig.shape == (24, 5)
    assert sig.notna().all().all()
    assert sig.min().min() >= -1.0
    assert sig.max().max() <= 1.0


def test_options_flow_point_in_time():
    base = OptionsFlowSignal().compute(_data_with_pcr(seed=1))

    shocked_data = _data_with_pcr(seed=1)
    k = 15
    shocked_data.option_chain.iloc[k:] *= 50.0   # shock future option data
    shocked = OptionsFlowSignal().compute(shocked_data)

    # signal strictly before the shock must be unchanged (no future leakage)
    pd.testing.assert_frame_equal(base.iloc[:k], shocked.iloc[:k])


def test_options_flow_neutral_when_absent():
    data = make_synthetic_data(n_tickers=10, n_months=36, seed=3)  # no option data
    with pytest.warns(OptionsDataWarning):
        sig = OptionsFlowSignal().compute(data)
    assert (sig == 0.0).all().all()
    assert sig.shape == data.prices.shape


def test_options_flow_low_pcr_is_bullish():
    """A name with persistently low PCR should score above a high-PCR name."""
    dates = pd.date_range("2020-01-31", periods=12, freq="ME")
    tickers = ["LOW", "MID", "HIGH"]
    prices = pd.DataFrame(100.0, index=dates, columns=tickers)
    pcr = pd.DataFrame(
        {"LOW": [0.5] * 12, "MID": [1.0] * 12, "HIGH": [1.8] * 12},
        index=dates,
    )
    data = MarketData(prices=prices, sectors=pd.Series("X", index=tickers),
                      option_chain=pcr)

    sig = OptionsFlowSignal(squash=False).compute(data)
    last = sig.iloc[-1]
    assert last["LOW"] > last["HIGH"]
