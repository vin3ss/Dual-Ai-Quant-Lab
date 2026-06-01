"""Smart-money / money-flow proxies from price + volume (free data we already have).

These are CRUDE monthly proxies, useful as a decision-support overlay — NOT validated
alpha and NOT used in the backtest. The richer institutional signals (FII/DII, bulk/block
deals, delivery %, F&O open-interest) live in separate free NSE files not yet ingested;
hooks for them are noted in the monitor. Everything here is point-in-time (trailing,
shifted) so a "latest" read uses only data up to that bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def volume_spike(prices: pd.DataFrame, volume: pd.DataFrame, lookback: int = 6) -> pd.DataFrame:
    """Volume relative to its trailing median (per ticker). >1.5 = elevated activity,
    a crude 'something is happening here' flag. Baseline is shifted one bar (PiT)."""
    base = volume.rolling(lookback, min_periods=2).median().shift(1)
    return (volume / base.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)


def money_flow(prices: pd.DataFrame, volume: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """Accumulation/distribution proxy in [-1, 1]: sign(return) * volume summed over the
    trailing window, normalized by total volume. Positive = up-moves on higher volume
    (accumulation); negative = down-moves on volume (distribution)."""
    ret = prices.pct_change(fill_method=None)
    signed = np.sign(ret) * volume
    num = signed.rolling(lookback, min_periods=2).sum()
    den = volume.rolling(lookback, min_periods=2).sum().replace(0.0, np.nan)
    return (num / den).clip(-1.0, 1.0)


def smart_money_score(prices: pd.DataFrame, volume: pd.DataFrame,
                      vol_lookback: int = 6, flow_lookback: int = 3) -> pd.DataFrame:
    """Combine into a single [-1, 1]-ish read: money-flow direction, amplified when
    volume is elevated. High positive = accumulation on a volume spike."""
    spike = volume_spike(prices, volume, vol_lookback)
    flow = money_flow(prices, volume, flow_lookback)
    amp = spike.clip(upper=3.0).fillna(1.0) / 1.5  # >1 when volume elevated
    return (flow * amp).clip(-1.5, 1.5)
