"""Options-flow alpha — OI, PCR, FII derivative positioning.

INTERFACE STUB. Evidence suggests this works best as a *filter/overlay* on a
price or factor signal rather than a standalone alpha. Consider emitting a
[-1, 1] conviction multiplier instead of a raw cross-sectional score.
"""
from __future__ import annotations
import pandas as pd
from ..base import AlphaSignal


class OptionsFlowSignal(AlphaSignal):
    name = "options_flow"

    def compute(self, data) -> pd.DataFrame:
        raise NotImplementedError(
            "Implement options-flow signal from data.option_chain (OI, PCR) and "
            "data.fii_deriv. Lag to the data timestamp; beware stale EOD snapshots."
        )
