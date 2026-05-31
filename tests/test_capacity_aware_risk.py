import pandas as pd
import pytest

from nse_alpha_forge.config import Config
from nse_alpha_forge.risk.manager import RiskManager
from nse_alpha_forge.backtest.engine import Backtester


def test_capacity_aware_sizing_redistributes_clipped_capital():
    dates = pd.date_range("2024-01-31", periods=6, freq="ME")
    cols = ["A", "B", "C"]

    target = pd.DataFrame(0.0, index=dates, columns=cols)
    target.loc[dates[-1], "A"] = 1.0

    scores = pd.DataFrame({"A": [3.0] * 6, "B": [2.0] * 6, "C": [1.0] * 6}, index=dates)
    prices = pd.DataFrame(100.0, index=dates, columns=cols)
    # A has tiny capacity; B/C can absorb clipped capital.
    volume = pd.DataFrame(
        {"A": [100.0] * 6, "B": [1_000_000.0] * 6, "C": [1_000_000.0] * 6}, index=dates
    )

    rm = RiskManager(Config().risk)
    out = rm.capacity_aware_targets(
        target_weights=target, prices=prices, volume=volume,
        portfolio_value=1_000_000.0, max_adv_participation=0.10,
        candidate_scores=scores, adv_window=3,
    )

    last = out.loc[dates[-1]]
    assert last["A"] < 1.0
    assert last[["B", "C"]].sum() > 0.0
    assert last.sum() == pytest.approx(1.0)


def test_capacity_aware_sizing_tracks_target_when_capacity_exists():
    dates = pd.date_range("2024-01-31", periods=8, freq="ME")
    cols = ["A", "B", "C", "D"]
    target = pd.DataFrame(
        {c: [0, 0, 0, 0, 0.25, 0.25, 0.25, 0.25] for c in cols}, index=dates
    )
    scores = pd.DataFrame(
        {"A": [4.0] * 8, "B": [3.0] * 8, "C": [2.0] * 8, "D": [1.0] * 8}, index=dates
    )
    prices = pd.DataFrame(100.0, index=dates, columns=cols)
    volume = pd.DataFrame(10_000_000.0, index=dates, columns=cols)

    rm = RiskManager(Config().risk)
    out = rm.capacity_aware_targets(
        target_weights=target, prices=prices, volume=volume,
        portfolio_value=1_000_000.0, max_adv_participation=0.10,
        candidate_scores=scores, adv_window=3,
    )

    gap = (target.abs().sum(axis=1) - out.abs().sum(axis=1)).abs()
    assert gap.loc[dates[4:]].max() < 1e-9


def test_backtester_reports_target_vs_executed_exposure():
    dates = pd.date_range("2024-01-31", periods=5, freq="ME")
    returns = pd.DataFrame({"A": [0.0, 0.01, 0.01, 0.01, 0.01]}, index=dates)
    weights = pd.DataFrame({"A": [0.0, 0.5, 0.5, 0.5, 0.5]}, index=dates)
    prices = pd.DataFrame({"A": [100.0] * 5}, index=dates)
    volume = pd.DataFrame({"A": [1_000_000.0] * 5}, index=dates)

    result = Backtester(Config()).run(weights=weights, returns=returns,
                                      prices=prices, volume=volume)
    for k in ("avg_target_exposure", "avg_executed_exposure",
              "avg_applied_exposure", "avg_exposure_gap"):
        assert k in result.stats
