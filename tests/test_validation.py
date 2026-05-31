import pandas as pd

from nse_alpha_forge.backtest.validation import (
    walk_forward,
    holdout_split,
    regime_stress,
    parameter_sensitivity,
)
from nse_alpha_forge.config import Config
from nse_alpha_forge.data import MarketData


def _validation_data() -> MarketData:
    dates = pd.date_range("2020-01-31", periods=48, freq="ME")

    # AAA wins in first half, loses in second half. BBB does the opposite.
    aaa_ret = [0.03] * 24 + [-0.03] * 24
    bbb_ret = [-0.01] * 24 + [0.03] * 24

    prices = pd.DataFrame(
        {
            "AAA": 100 * pd.Series([1 + r for r in aaa_ret], index=dates).cumprod(),
            "BBB": 100 * pd.Series([1 + r for r in bbb_ret], index=dates).cumprod(),
        },
        index=dates,
    )

    sectors = pd.Series({"AAA": "IT", "BBB": "BANK"}, name="sector")

    volume = pd.DataFrame(
        {"AAA": [1_000_000] * 48, "BBB": [1_000_000] * 48},
        index=dates,
    )

    return MarketData(prices=prices, sectors=sectors, volume=volume)


def _weights_fn(data: MarketData, params: dict | None = None) -> pd.DataFrame:
    ticker = (params or {}).get("ticker", "AAA")
    w = pd.DataFrame(0.0, index=data.prices.index, columns=data.prices.columns)
    if ticker in w.columns:
        w[ticker] = 1.0
    return w


def test_walk_forward_returns_oos_only():
    data = _validation_data()
    cfg = Config()

    result = walk_forward(
        weights_fn=_weights_fn,
        data=data,
        cfg=cfg,
        train_window=12,
        test_window=6,
        step=6,
        param_grid={"ticker": ["AAA", "BBB"]},
    )

    assert result.result.returns.index.min() >= data.prices.index[12]
    assert len(result.result.returns) == 36
    assert len(result.windows) == 6
    assert len(result.selected_params) == 6


def test_holdout_split_is_disjoint():
    data = _validation_data()
    cfg = Config()

    result = holdout_split(
        weights_fn=_weights_fn,
        data=data,
        cfg=cfg,
        split=0.5,
        params={"ticker": "AAA"},
    )

    is_idx = set(result["is_result"].returns.index)
    oos_idx = set(result["oos_result"].returns.index)

    assert is_idx.isdisjoint(oos_idx)
    assert max(is_idx) < min(oos_idx)


def test_overfit_param_has_large_is_oos_gap():
    data = _validation_data()
    cfg = Config()

    # AAA is excellent IS and bad OOS by construction.
    result = holdout_split(
        weights_fn=_weights_fn,
        data=data,
        cfg=cfg,
        split=0.5,
        params={"ticker": "AAA"},
    )

    gap = result["overfitting_gap"]["sharpe_degradation"]
    assert gap > 1.0


def test_regime_stress_returns_per_window_stats():
    data = _validation_data()
    cfg = Config()

    out = regime_stress(
        weights_fn=_weights_fn,
        data=data,
        cfg=cfg,
        windows={
            "early": ("2020-01-31", "2021-12-31"),
            "late": ("2022-01-31", "2023-12-31"),
        },
        params={"ticker": "AAA"},
    )

    assert set(out.index) == {"early", "late"}
    assert "sharpe" in out.columns
    assert "max_dd" in out.columns


def test_parameter_sensitivity_flags_fragility():
    data = _validation_data()
    cfg = Config()

    out = parameter_sensitivity(
        weights_fn=_weights_fn,
        data=data,
        cfg=cfg,
        param_grid={"ticker": ["AAA", "BBB"]},
        split=0.5,
        metric="sharpe",
        fragility_threshold=0.5,
    )

    assert len(out) == 2
    assert out["fragile"].all()
    assert out["oos_sharpe"].max() != out["oos_sharpe"].min()
