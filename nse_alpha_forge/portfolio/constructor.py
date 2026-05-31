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
