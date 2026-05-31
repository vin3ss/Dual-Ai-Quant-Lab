"""Point-in-time liquid-universe selection (issue #19).

Restricts the cross-section to the top-N names by trailing turnover so signals
aren't dominated by illiquid microcaps (which are noise and untradeable). The
ranking is lagged one bar so eligibility at date t uses only past liquidity.
"""

from __future__ import annotations

import warnings
import pandas as pd


def liquid_universe_mask(prices: pd.DataFrame, volume: pd.DataFrame | None,
                         top_n: int = 300, lookback: int = 6) -> pd.DataFrame:
    """Boolean date x ticker mask: True where a name is in the top-N by trailing
    average turnover (price*volume), point-in-time (shifted one bar)."""
    if volume is None:
        warnings.warn(
            "liquid_universe_mask: no volume supplied; cannot rank liquidity, "
            "returning all-True (no filter).", RuntimeWarning, stacklevel=2,
        )
        return pd.DataFrame(True, index=prices.index, columns=prices.columns)

    turnover = (prices * volume.reindex_like(prices)).astype(float)
    adv = turnover.rolling(lookback, min_periods=1).mean().shift(1)  # point-in-time
    rank = adv.rank(axis=1, ascending=False, method="first")
    return rank.le(top_n).fillna(False)


def apply_liquidity_filter(signal: pd.DataFrame, prices: pd.DataFrame,
                           volume: pd.DataFrame | None, top_n: int = 300,
                           lookback: int = 6) -> pd.DataFrame:
    """Blank out signal values for names outside the point-in-time liquid set."""
    mask = liquid_universe_mask(prices, volume, top_n=top_n, lookback=lookback)
    return signal.where(mask.reindex_like(signal).fillna(False))


def constituent_mask(price_index: pd.DatetimeIndex, columns: pd.Index,
                     constituents: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time index-membership mask from a constituents table (issue #21).

    This is the RIGID, non-discretionary universe Gemini called for — it removes
    the turnover/liquidity pre-selection bias because membership is set by the
    index provider, not by recent price action.

    `constituents` accepts either schema:
      - snapshot:  columns [date, symbol]  (members as of each reconstitution date)
      - interval:  columns [symbol, start_date, end_date]  (end_date blank = still in)

    Returns a boolean date x ticker mask; at date t a name is True iff it was an
    index member as of t (using the most recent snapshot <= t, or its interval).
    """
    cols = list(columns)
    mask = pd.DataFrame(False, index=price_index, columns=cols)
    c = constituents.copy()
    c.columns = [str(x).lower().strip() for x in c.columns]

    if {"start_date"}.issubset(c.columns):  # interval schema
        c["symbol"] = c["symbol"].astype(str).str.upper().str.strip()
        c["start_date"] = pd.to_datetime(c["start_date"])
        c["end_date"] = pd.to_datetime(c.get("end_date"))
        for _, r in c.iterrows():
            if r["symbol"] not in mask.columns:
                continue
            end = r["end_date"] if pd.notna(r["end_date"]) else price_index.max()
            sel = (price_index >= r["start_date"]) & (price_index <= end)
            mask.loc[sel, r["symbol"]] = True
        return mask

    # snapshot schema
    c["date"] = pd.to_datetime(c["date"])
    c["symbol"] = c["symbol"].astype(str).str.upper().str.strip()
    snap_dates = sorted(c["date"].unique())
    members_by_date = {d: set(c.loc[c["date"] == d, "symbol"]) for d in snap_dates}
    for t in price_index:
        valid = [d for d in snap_dates if d <= t]
        if not valid:
            continue
        members = members_by_date[valid[-1]]
        present = [col for col in cols if col in members]
        mask.loc[t, present] = True
    return mask


def apply_constituent_filter(signal: pd.DataFrame,
                             constituents: pd.DataFrame) -> pd.DataFrame:
    """Blank out signal values for names outside the point-in-time index membership."""
    mask = constituent_mask(signal.index, signal.columns, constituents)
    return signal.where(mask.reindex_like(signal).fillna(False))
