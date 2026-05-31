import pandas as pd
import pytest

from nse_alpha_forge.config import Config
from nse_alpha_forge.backtest.costs import (
    transaction_costs,
    estimate_participation,
    CostModelWarning,
)
from nse_alpha_forge.backtest.engine import Backtester


def test_costs_scale_with_turnover():
    cfg = Config()

    dates = pd.date_range("2024-01-31", periods=2, freq="ME")
    small = pd.DataFrame({"AAA": [0.01, 0.00]}, index=dates)
    large = pd.DataFrame({"AAA": [0.10, 0.00]}, index=dates)

    _, small_cost = transaction_costs(small, cfg.cost, clip_to_capacity=False)
    _, large_cost = transaction_costs(large, cfg.cost, clip_to_capacity=False)

    assert large_cost.total.sum() > small_cost.total.sum()
    assert large_cost.explicit.sum() > small_cost.explicit.sum()


def test_impact_rises_with_participation():
    cfg = Config()

    dates = pd.date_range("2024-01-31", periods=25, freq="ME")
    delta = pd.DataFrame({"AAA": [0.0] * 24 + [0.10]}, index=dates)
    prices = pd.DataFrame({"AAA": [100.0] * 25}, index=dates)

    high_volume = pd.DataFrame({"AAA": [1_000_000.0] * 25}, index=dates)
    low_volume = pd.DataFrame({"AAA": [1_000.0] * 25}, index=dates)

    _, low_part_cost = transaction_costs(
        delta,
        cfg.cost,
        prices=prices,
        volume=high_volume,
        portfolio_value=cfg.cost.portfolio_value,
        clip_to_capacity=False,
    )

    _, high_part_cost = transaction_costs(
        delta,
        cfg.cost,
        prices=prices,
        volume=low_volume,
        portfolio_value=cfg.cost.portfolio_value,
        clip_to_capacity=False,
    )

    assert high_part_cost.impact.iloc[-1] > low_part_cost.impact.iloc[-1]


def test_capacity_cap_engages_and_clips_trade():
    cfg = Config()
    cfg.cost.max_adv_participation = 0.05

    dates = pd.date_range("2024-01-31", periods=25, freq="ME")
    delta = pd.DataFrame({"AAA": [0.0] * 24 + [1.00]}, index=dates)
    prices = pd.DataFrame({"AAA": [100.0] * 25}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000.0] * 25}, index=dates)

    with pytest.warns(CostModelWarning, match="Capacity cap engaged"):
        clipped, costs = transaction_costs(
            delta,
            cfg.cost,
            prices=prices,
            volume=volume,
            portfolio_value=cfg.cost.portfolio_value,
            clip_to_capacity=True,
        )

    assert costs.clipped_trades is not None
    assert costs.clipped_trades.iloc[-1, 0]
    assert clipped.iloc[-1, 0] < delta.iloc[-1, 0]


def test_backtester_accepts_volume_and_capacity_inputs():
    cfg = Config()
    cfg.cost.max_adv_participation = 0.05

    dates = pd.date_range("2024-01-31", periods=25, freq="ME")
    weights = pd.DataFrame({"AAA": [0.0] * 24 + [1.0]}, index=dates)
    returns = pd.DataFrame({"AAA": [0.01] * 25}, index=dates)
    prices = pd.DataFrame({"AAA": [100.0] * 25}, index=dates)
    volume = pd.DataFrame({"AAA": [1_000.0] * 25}, index=dates)

    with pytest.warns(CostModelWarning):
        result = Backtester(cfg).run(
            weights,
            returns,
            prices=prices,
            volume=volume,
        )

    assert result.cost_breakdown is not None
    assert result.stats["capacity_clips"] >= 1
    assert result.turnover.iloc[-1] < 1.0
