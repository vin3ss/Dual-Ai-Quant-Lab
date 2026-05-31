"""Validation harness for NSE Alpha Forge.

Pure functions over `(weights_fn, data)`. The harness never lets test data
choose parameters. Selection/refit happens only on train windows; evaluation is
held-out.

Validation can still lie:
- overlapping walk-forward windows reduce independence;
- repeated parameter-grid searches create multiple-testing bias;
- hand-picked stress windows can become cherry-picked narratives;
- synthetic data hides real liquidity, delisting, and revision problems.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable

import pandas as pd

from ..config import Config
from ..data.market_data import MarketData
from .engine import Backtester, BacktestResult


WeightsFn = Callable[[MarketData, dict | None], pd.DataFrame]


@dataclass
class ValidationResult:
    result: BacktestResult
    selected_params: list[dict]
    windows: pd.DataFrame
    stats: dict


def _param_grid(grid: dict | None) -> list[dict | None]:
    if not grid:
        return [None]
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in product(*(grid[k] for k in keys))]


def _slice_data(data: MarketData, start, end, lookback: int = 0) -> MarketData:
    """Slice MarketData to [start,end], optionally prepending historical context.

    The prepended lookback bars are for feature/signal computation only. Callers
    must trim weights/returns back to the true scored window before evaluation.
    """
    full_idx = data.prices.index
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    if start_ts not in full_idx or end_ts not in full_idx:
        window_idx = data.prices.loc[start_ts:end_ts].index
        if window_idx.empty:
            raise ValueError("Requested slice has no matching dates.")
        start_pos = full_idx.get_loc(window_idx[0])
        end_pos = full_idx.get_loc(window_idx[-1])
    else:
        start_pos = full_idx.get_loc(start_ts)
        end_pos = full_idx.get_loc(end_ts)

    buffer_start = max(0, start_pos - max(lookback, 0))
    idx = full_idx[buffer_start:end_pos + 1]

    def frame(x):
        if x is None:
            return None
        return x.reindex(idx)

    fundamentals = {
        k: v.reindex(idx) for k, v in data.fundamentals.items()
    }

    return MarketData(
        prices=data.prices.reindex(idx),
        sectors=data.sectors,
        fundamentals=fundamentals,
        option_chain=frame(data.option_chain),
        fii_deriv=frame(data.fii_deriv),
        macro=frame(data.macro),
        news=frame(data.news),
        volume=frame(getattr(data, "volume", None)),
    )


def _run(
    weights_fn: WeightsFn,
    data: MarketData,
    cfg: Config,
    params: dict | None,
) -> BacktestResult:
    weights = weights_fn(data, params)
    returns = data.returns()
    return Backtester(cfg).run(
        weights=weights,
        returns=returns,
        prices=data.prices,
        volume=getattr(data, "volume", None),
    )


def _run_scored_window(
    weights_fn: WeightsFn,
    data_with_context: MarketData,
    score_index: pd.Index,
    cfg: Config,
    params: dict | None,
) -> BacktestResult:
    """Compute weights with context, evaluate only on score_index."""
    weights_full = weights_fn(data_with_context, params)

    weights = weights_full.reindex(score_index)
    prices = data_with_context.prices.reindex(score_index)
    returns = data_with_context.returns().reindex(score_index)
    volume = (
        data_with_context.volume.reindex(score_index)
        if getattr(data_with_context, "volume", None) is not None
        else None
    )

    return Backtester(cfg).run(
        weights=weights,
        returns=returns,
        prices=prices,
        volume=volume,
    )


def _metric(stats: dict, name: str) -> float:
    if name not in stats:
        raise KeyError(f"Metric {name!r} not found in stats.")
    return float(stats[name])


def _select_params(
    weights_fn: WeightsFn,
    train_data: MarketData,
    cfg: Config,
    params_list: list[dict | None],
    metric: str,
) -> dict | None:
    best_params = params_list[0]
    best_value = float("-inf")

    for params in params_list:
        result = _run(weights_fn, train_data, cfg, params)
        value = _metric(result.stats, metric)
        if value > best_value:
            best_value = value
            best_params = params

    return best_params


def walk_forward(
    weights_fn: WeightsFn,
    data: MarketData,
    cfg: Config,
    train_window: int,
    test_window: int,
    step: int | None = None,
    param_grid: dict | None = None,
    metric: str = "sharpe",
    lookback: int = 0,
) -> ValidationResult:
    """Rolling train/test validation.

    At each split:
    1. Choose parameters using only the train slice.
    2. Evaluate selected parameters only on the next held-out test slice.
    3. Concatenate OOS test returns.
    """
    if train_window <= 0 or test_window <= 0:
        raise ValueError("train_window and test_window must be positive")

    step = step or test_window
    idx = data.prices.index
    params_list = _param_grid(param_grid)

    oos_returns = []
    oos_turnover = []
    oos_equity_parts = []
    selected = []
    rows = []

    start = 0
    while start + train_window + test_window <= len(idx):
        train_idx = idx[start:start + train_window]
        test_idx = idx[start + train_window:start + train_window + test_window]

        train_data = _slice_data(data, train_idx[0], train_idx[-1], lookback=lookback)
        test_data = _slice_data(data, test_idx[0], test_idx[-1], lookback=lookback)

        chosen = _select_params(weights_fn, train_data, cfg, params_list, metric)
        result = _run_scored_window(
            weights_fn=weights_fn,
            data_with_context=test_data,
            score_index=test_idx,
            cfg=cfg,
            params=chosen,
        )

        oos_returns.append(result.returns)
        oos_turnover.append(result.turnover)
        oos_equity_parts.append(result.equity_curve)
        selected.append(chosen or {})

        rows.append(
            {
                "train_start": train_idx[0],
                "train_end": train_idx[-1],
                "test_start": test_idx[0],
                "test_end": test_idx[-1],
                "selected_params": chosen or {},
            }
        )

        start += step

    if not oos_returns:
        raise ValueError("No walk-forward windows generated.")

    returns = pd.concat(oos_returns).sort_index()
    turnover = pd.concat(oos_turnover).sort_index()
    equity = (1.0 + returns).cumprod()

    stats = Backtester(cfg)._stats(returns, equity, turnover)
    result = BacktestResult(equity, returns, turnover, stats)

    return ValidationResult(
        result=result,
        selected_params=selected,
        windows=pd.DataFrame(rows),
        stats=stats,
    )


def holdout_split(
    weights_fn: WeightsFn,
    data: MarketData,
    cfg: Config,
    split: float | pd.Timestamp,
    params: dict | None = None,
) -> dict:
    """Simple in-sample / out-of-sample split."""
    idx = data.prices.index

    if isinstance(split, float):
        if not 0 < split < 1:
            raise ValueError("float split must be in (0,1)")
        cut = int(len(idx) * split)
        train_idx = idx[:cut]
        test_idx = idx[cut:]
    else:
        split_ts = pd.Timestamp(split)
        train_idx = idx[idx < split_ts]
        test_idx = idx[idx >= split_ts]

    if len(train_idx) == 0 or len(test_idx) == 0:
        raise ValueError("Split produced empty IS or OOS window.")

    is_data = _slice_data(data, train_idx[0], train_idx[-1])
    oos_data = _slice_data(data, test_idx[0], test_idx[-1])

    is_result = _run(weights_fn, is_data, cfg, params)
    oos_result = _run(weights_fn, oos_data, cfg, params)

    gap = is_result.stats["sharpe"] - oos_result.stats["sharpe"]

    return {
        "is_result": is_result,
        "oos_result": oos_result,
        "is_stats": is_result.stats,
        "oos_stats": oos_result.stats,
        "overfitting_gap": {
            "is_sharpe": is_result.stats["sharpe"],
            "oos_sharpe": oos_result.stats["sharpe"],
            "sharpe_degradation": gap,
        },
    }


def regime_stress(
    weights_fn: WeightsFn,
    data: MarketData,
    cfg: Config,
    windows: dict[str, tuple[str | pd.Timestamp, str | pd.Timestamp]],
    params: dict | None = None,
) -> pd.DataFrame:
    """Evaluate strategy over caller-supplied stress windows."""
    rows = []

    for name, (start, end) in windows.items():
        sub = _slice_data(data, pd.Timestamp(start), pd.Timestamp(end))
        result = _run(weights_fn, sub, cfg, params)
        row = {"window": name, **result.stats}
        rows.append(row)

    return pd.DataFrame(rows).set_index("window")


def parameter_sensitivity(
    weights_fn: WeightsFn,
    data: MarketData,
    cfg: Config,
    param_grid: dict,
    split: float | pd.Timestamp = 0.6,
    metric: str = "sharpe",
    fragility_threshold: float = 1.0,
) -> pd.DataFrame:
    """Report how much OOS metric moves across a parameter grid."""
    rows = []

    for params in _param_grid(param_grid):
        result = holdout_split(weights_fn, data, cfg, split=split, params=params)
        oos_value = _metric(result["oos_stats"], metric)
        is_value = _metric(result["is_stats"], metric)
        rows.append(
            {
                "params": params,
                f"is_{metric}": is_value,
                f"oos_{metric}": oos_value,
                "gap": is_value - oos_value,
            }
        )

    out = pd.DataFrame(rows)
    spread = out[f"oos_{metric}"].max() - out[f"oos_{metric}"].min()
    out["oos_metric_spread"] = spread
    out["fragile"] = spread > fragility_threshold
    return out
