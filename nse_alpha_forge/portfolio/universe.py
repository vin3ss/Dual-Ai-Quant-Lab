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
