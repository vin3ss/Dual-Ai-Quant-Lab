"""Macro alpha — RBI rates, CPI, IIP, money supply tilts.

INTERFACE STUB. Macro is usually a *regime/tilt* input rather than a per-stock
signal; consider emitting sector tilts (rate-sensitive vs defensive) here.
"""
from __future__ import annotations
import pandas as pd
from ..base import AlphaSignal


class MacroSignal(AlphaSignal):
    name = "macro"

    def compute(self, data) -> pd.DataFrame:
        raise NotImplementedError(
            "Implement macro tilt: map data.macro (RBI/CPI series, lagged to "
            "release date) to per-sector or per-name tilts."
        )
