"""Options-flow alpha — OI / PCR / FII-derivative positioning as an OVERLAY.

Evidence (see Research/AlphaIdeas/indian_quant_research_review.md): options flow
works best as a *conviction overlay* on a price/factor signal, not as a standalone
alpha. So `compute` returns a bounded [-1, 1] conviction score (tanh-squashed),
small in scale by design relative to the z-scored core signals — it nudges, it
doesn't dominate.

Point-in-time: every input is lagged one bar (`.shift(1)`). EOD option snapshots
are often stale and expiry effects distort OI/PCR, so the same-bar value must
never be used.

Expected (all optional; signal degrades to neutral if absent):
    data.option_chain : date x ticker DataFrame of Put-Call Ratio (PCR) per
                        underlying. Low PCR (call-heavy) is read as bullish.
    data.fii_deriv    : date x ticker DataFrame of FII net derivative positioning
                        per underlying. Positive (net long) is read as bullish.
                        A market-wide (single-column) series is ignored here — that
                        belongs in the regime/macro modules, not a cross-sectional
                        signal.
"""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd

from ..base import AlphaSignal


class OptionsDataWarning(RuntimeWarning):
    """Options/flow data is missing or low-quality in a way that can bias results."""


class OptionsFlowSignal(AlphaSignal):
    name = "options_flow"

    def __init__(
        self,
        pcr_weight: float = 1.0,
        fii_weight: float = 1.0,
        winsor_limits: float = 0.02,
        squash: bool = True,
    ):
        self.pcr_weight = pcr_weight
        self.fii_weight = fii_weight
        self.winsor_limits = winsor_limits
        self.squash = squash

    @staticmethod
    def _per_ticker(frame, index, columns):
        """Return a date x ticker frame if `frame` is a usable per-ticker panel,
        else None. Single-column (market-wide) frames are rejected on purpose."""
        if isinstance(frame, pd.DataFrame) and not frame.empty and frame.shape[1] > 1:
            return frame.reindex(index=index, columns=columns)
        return None

    def compute(self, data) -> pd.DataFrame:
        prices = data.prices
        terms: list[pd.DataFrame] = []

        pcr = self._per_ticker(getattr(data, "option_chain", None),
                               prices.index, prices.columns)
        if pcr is not None:
            # low PCR (call-heavy positioning) = bullish -> negate, lagged one bar
            terms.append(-self.pcr_weight * self.zscore(pcr.shift(1)))

        fii = self._per_ticker(getattr(data, "fii_deriv", None),
                               prices.index, prices.columns)
        if fii is not None:
            # positive FII net derivative positioning = bullish, lagged one bar
            terms.append(self.fii_weight * self.zscore(fii.shift(1)))

        if not terms:
            warnings.warn(
                "OptionsFlowSignal: no per-ticker option_chain/fii_deriv supplied; "
                "returning a neutral (zero) overlay. This signal is inert until "
                "options data is connected.",
                OptionsDataWarning,
                stacklevel=2,
            )
            return pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        combined = sum(terms) / len(terms)
        combined = self.winsorize(self.zscore(combined), limits=self.winsor_limits)

        if self.squash:
            combined = np.tanh(combined)

        # Missing per-name data -> neutral (0), so absent options data never drops a name.
        return combined.fillna(0.0)
