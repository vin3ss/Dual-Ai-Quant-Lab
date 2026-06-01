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


# --- richer "big fish" consumers (from free NSE files via fetch_smart_money.py) ---

def delivery_accumulation(delivery_pct: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """Trailing delivery-% vs its own baseline. High & rising delivery % = conviction
    holding (not intraday churn) — an accumulation tell. delivery_pct is date x ticker
    (% of traded volume taken to delivery). Returns z-like ratio, PiT (shifted)."""
    base = delivery_pct.rolling(12, min_periods=3).mean().shift(1)
    recent = delivery_pct.rolling(lookback, min_periods=1).mean().shift(1)
    return (recent / base.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)


def deal_pressure(deals: pd.DataFrame, index: pd.DatetimeIndex,
                  columns: pd.Index) -> pd.DataFrame:
    """Net bulk/block-deal pressure per ticker per period, in [-1, 1].

    `deals` columns: date, symbol, action ('BUY'/'SELL'), quantity. Aggregates signed
    quantity per (period, symbol) and normalizes by gross dealt quantity. Positive = net
    institutional buying. Resampled to the price index (month-end here).
    """
    d = deals.copy()
    d.columns = [c.lower().strip() for c in d.columns]
    d["date"] = pd.to_datetime(d["date"])
    d["symbol"] = d["symbol"].astype(str).str.upper().str.strip()
    sign = d["action"].astype(str).str.upper().str.startswith("B").map({True: 1, False: -1})
    d["signed"] = sign * d["quantity"].astype(float)
    d["gross"] = d["quantity"].astype(float)

    out = pd.DataFrame(0.0, index=index, columns=columns)
    # assign each deal to the period (month-end) it falls in
    period = d["date"].dt.to_period("M").dt.to_timestamp("M")
    grp = d.groupby([period, "symbol"]).agg(net=("signed", "sum"), gross=("gross", "sum"))
    for (dt, sym), row in grp.iterrows():
        if sym in out.columns and dt in out.index and row["gross"] > 0:
            out.loc[dt, sym] = float(row["net"] / row["gross"])
    return out.clip(-1.0, 1.0)
