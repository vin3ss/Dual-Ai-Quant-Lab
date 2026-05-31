import pandas as pd

from nse_alpha_forge.data import make_synthetic_data
from nse_alpha_forge.alpha.regime import RegimeDetector


def test_regime_detector_returns_bounded_series():
    data = make_synthetic_data(n_tickers=20, n_months=80, seed=42)

    detector = RegimeDetector()
    regime = detector.detect(data)

    assert isinstance(regime, pd.Series)
    assert regime.index.equals(data.prices.index)
    assert regime.name == "regime_multiplier"
    assert regime.min() >= 0.0
    assert regime.max() <= 1.0


def test_regime_detector_is_point_in_time_no_same_date_close_leakage():
    data = make_synthetic_data(n_tickers=20, n_months=80, seed=42)

    detector = RegimeDetector()
    baseline = detector.detect(data)

    shocked = make_synthetic_data(n_tickers=20, n_months=80, seed=42)
    last_date = shocked.prices.index[-1]
    shocked.prices.loc[last_date] *= 10.0

    shocked_result = detector.detect(shocked)

    assert baseline.loc[last_date] == shocked_result.loc[last_date]
