"""Regime detection — gate or scale exposure by market state.

INTERFACE STUB. Unlike the other modules this returns a per-date scalar (or
small state vector), not a cross-sectional score. Momentum crashes after sharp
reversals, so a regime gate that de-risks in high-vol / falling-trend states is
one of the highest-value additions.
"""
from __future__ import annotations
import pandas as pd


class RegimeDetector:
    name = "regime"

    def detect(self, data) -> pd.Series:
        """Return a per-date risk multiplier in [0, 1] (1 = risk-on, 0 = flat).

        Suggested inputs: NIFTY trend (above/below 200dma), realized vol,
        India VIX, FII/DII flows.
        """
        raise NotImplementedError(
            "Implement regime detection -> per-date risk multiplier in [0,1]."
        )
