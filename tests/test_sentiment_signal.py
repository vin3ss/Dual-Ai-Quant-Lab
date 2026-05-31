import pandas as pd
import pytest

from nse_alpha_forge.alpha.sentiment import SentimentSignal, SentimentDataWarning
from nse_alpha_forge.data import MarketData, make_synthetic_data


def _sentiment_fixture() -> MarketData:
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    tickers = ["GOOD", "MID", "BAD"]

    prices = pd.DataFrame(
        {
            "GOOD": [100, 101, 102, 103, 104, 105, 106, 107],
            "MID": [100, 100, 100, 100, 100, 100, 100, 100],
            "BAD": [100, 99, 98, 97, 96, 95, 94, 93],
        },
        index=dates,
    )

    sectors = pd.Series(
        {
            "GOOD": "IT",
            "MID": "FMCG",
            "BAD": "BANK",
        },
        name="sector",
    )

    news = pd.DataFrame(
        {
            "GOOD": [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6],
            "MID": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "BAD": [-0.2, -0.4, -0.6, -0.8, -1.0, -1.2, -1.4, -1.6],
        },
        index=dates,
    )

    return MarketData(prices=prices, sectors=sectors, news=news)


def test_sentiment_neutral_when_absent():
    data = make_synthetic_data(n_tickers=8, n_months=24, seed=21)

    with pytest.warns(SentimentDataWarning, match="data.news is absent"):
        out = SentimentSignal().compute(data)

    assert out.shape == data.prices.shape
    assert (out == 0.0).all().all()


def test_sentiment_output_bounded_and_finite():
    data = _sentiment_fixture()
    out = SentimentSignal().compute(data)

    assert out.index.equals(data.prices.index)
    assert out.columns.equals(data.prices.columns)
    assert out.notna().all().all()
    assert out.max().max() <= 3.0
    assert out.min().min() >= -3.0


def test_sentiment_point_in_time_future_shock_does_not_change_past():
    base_data = _sentiment_fixture()
    shocked_data = _sentiment_fixture()

    k = 5
    shocked_data.news.iloc[k:] = shocked_data.news.iloc[k:] * 100.0

    base = SentimentSignal().compute(base_data)
    shocked = SentimentSignal().compute(shocked_data)

    pd.testing.assert_frame_equal(base.iloc[:k], shocked.iloc[:k])


def test_higher_input_sentiment_gets_higher_score():
    data = _sentiment_fixture()
    out = SentimentSignal().compute(data)

    last = out.iloc[-1]

    assert last["GOOD"] > last["MID"]
    assert last["MID"] > last["BAD"]
