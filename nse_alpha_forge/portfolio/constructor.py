"""Blend alpha signals into target portfolio weights."""

from __future__ import annotations
import pandas as pd

from ..alpha.base import AlphaSignal
from ..config import StrategyConfig


class PortfolioConstructor:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    def combine(self, signals: dict[str, pd.DataFrame],
                weights: dict[str, float] | None = None) -> pd.DataFrame:
        """Weighted sum of standardized signals -> composite score."""
        weights = weights or {k: 1 / len(signals) for k in signals}
        composite = None
        for name, sig in signals.items():
            term = weights.get(name, 0) * sig
            composite = term if composite is None else composite.add(term, fill_value=0)
        return composite

    def to_weights(self, composite: pd.DataFrame,
                   sectors: pd.Series | None = None) -> pd.DataFrame:
        """Top-quantile long-only weights, optionally sector-neutralized."""
        if self.cfg.sector_neutral and sectors is not None:
            composite = AlphaSignal.sector_neutralize(composite, sectors)

        weights = pd.DataFrame(0.0, index=composite.index, columns=composite.columns)
        q = self.cfg.quantiles
        for dt, row in composite.iterrows():
            valid = row.dropna()
            if valid.empty:
                continue
            n_long = max(1, len(valid) // q)
            longs = valid.nlargest(n_long).index
            weights.loc[dt, longs] = 1.0 / n_long
            if not self.cfg.long_only:
                shorts = valid.nsmallest(n_long).index
                weights.loc[dt, shorts] = -1.0 / n_long
        return weights

    def apply_sector_tilt(self, weights: pd.DataFrame, macro_signal: pd.DataFrame | None,
                          sectors: pd.Series, strength: float = 0.25) -> pd.DataFrame:
        """Tilt SECTOR BUDGETS by a macro sector view (fixes issue #10).

        Macro is a per-sector tilt. Blending it into the composite score is
        useless under `sector_neutral=True` because sector-neutralization demeans
        within each sector and cancels a uniform per-sector value. Instead we apply
        it here, AFTER name selection, by scaling each name's weight by
        ``1 + strength * macro_tilt`` and renormalizing to preserve the original
        gross exposure. This changes how much capital each sector receives while
        leaving within-sector relative weights (the stock picks) untouched.

        `macro_signal` is the date x ticker frame from MacroSignal (uniform within
        a sector). Pass None / an all-zero frame to leave weights unchanged.
        """
        if macro_signal is None:
            return weights

        out = weights.copy()
        for dt, row in weights.iterrows():
            gross = row.abs().sum()
            if gross == 0 or dt not in macro_signal.index:
                continue
            tilt = macro_signal.loc[dt].reindex(row.index).fillna(0.0)
            mult = (1.0 + strength * tilt).clip(lower=0.0)  # no long-only sign flips
            tilted = row * mult
            new_gross = tilted.abs().sum()
            if new_gross > 0:
                tilted = tilted * (gross / new_gross)   # preserve gross exposure
            out.loc[dt] = tilted
        return out
