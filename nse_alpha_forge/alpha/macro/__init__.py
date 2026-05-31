"""Macro alpha — RBI rates, CPI, IIP, money supply tilts.

Macro is a sector tilt, not a standalone stock-selection alpha. It maps
release-date macro data into date x ticker scores through `data.sectors`.

Point-in-time rule:
Every macro input is shifted by one bar before use. The loader must index macro
data by release/availability date, not reference period.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd

from ..base import AlphaSignal


class MacroDataWarning(RuntimeWarning):
    """Macro data is missing or potentially biased."""


@dataclass(frozen=True)
class MacroConfig:
    rate_sensitive_sectors: tuple[str, ...] = ("BANK", "AUTO", "REALTY", "FINANCIALS")
    defensive_sectors: tuple[str, ...] = ("FMCG", "PHARMA", "IT", "HEALTHCARE")

    repo_weight: float = 0.45
    cpi_weight: float = 0.35
    iip_weight: float = 0.20

    repo_lookback: int = 3
    cpi_lookback: int = 3
    iip_lookback: int = 3

    repo_scale: float = 0.25
    cpi_scale: float = 0.50
    iip_scale: float = 2.00

    max_abs_tilt: float = 1.0
    neutral_value: float = 0.0


class MacroSignal(AlphaSignal):
    name = "macro"

    def __init__(self, cfg: MacroConfig | None = None):
        self.cfg = cfg or MacroConfig()

    def compute(self, data) -> pd.DataFrame:
        prices = data.prices
        sectors = data.sectors.reindex(prices.columns).fillna("UNKNOWN")
        macro = getattr(data, "macro", None)

        if macro is None or not isinstance(macro, pd.DataFrame) or macro.empty:
            warnings.warn(
                "MacroSignal: data.macro is absent; returning neutral macro tilt.",
                MacroDataWarning,
                stacklevel=2,
            )
            return self._neutral(prices.index, prices.columns)

        macro = self._prepare_macro(macro, prices.index)

        components: list[pd.Series] = []

        repo = self._first_existing(macro, ("repo_rate", "rbi_repo_rate", "policy_rate"))
        if repo is not None:
            # Falling rates are bullish for rate-sensitive sectors.
            repo_delta = macro[repo].diff(self.cfg.repo_lookback).shift(1)
            repo_score = (-repo_delta / self.cfg.repo_scale).clip(-1.0, 1.0)
            components.append(self.cfg.repo_weight * repo_score)

        cpi = self._first_existing(macro, ("cpi", "inflation", "headline_cpi"))
        if cpi is not None:
            # Falling inflation is pro-cyclical/rate-sensitive; rising inflation defensive.
            cpi_delta = macro[cpi].diff(self.cfg.cpi_lookback).shift(1)
            cpi_score = (-cpi_delta / self.cfg.cpi_scale).clip(-1.0, 1.0)
            components.append(self.cfg.cpi_weight * cpi_score)

        iip = self._first_existing(macro, ("iip", "industrial_production", "iip_growth"))
        if iip is not None:
            # Improving growth supports cyclicals/rate-sensitive sectors.
            iip_delta = macro[iip].diff(self.cfg.iip_lookback).shift(1)
            iip_score = (iip_delta / self.cfg.iip_scale).clip(-1.0, 1.0)
            components.append(self.cfg.iip_weight * iip_score)

        if not components:
            warnings.warn(
                "MacroSignal: data.macro has no supported repo_rate/cpi/iip columns; "
                "returning neutral macro tilt.",
                MacroDataWarning,
                stacklevel=2,
            )
            return self._neutral(prices.index, prices.columns)

        macro_score = sum(components).reindex(prices.index).fillna(self.cfg.neutral_value)
        macro_score = macro_score.clip(-self.cfg.max_abs_tilt, self.cfg.max_abs_tilt)

        sector_direction = self._sector_direction(sectors)
        out = pd.DataFrame(
            np.outer(macro_score.to_numpy(), sector_direction.to_numpy()),
            index=prices.index,
            columns=prices.columns,
        )

        return out.clip(-self.cfg.max_abs_tilt, self.cfg.max_abs_tilt).fillna(0.0)

    def _prepare_macro(self, macro: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
        frame = macro.copy()
        frame.columns = [str(c).lower().strip() for c in frame.columns]

        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.set_index("date")

        if not isinstance(frame.index, pd.DatetimeIndex):
            raise TypeError("data.macro must have a DatetimeIndex or a date column.")

        frame = frame.sort_index().reindex(index).ffill()
        return frame.astype(float)

    def _sector_direction(self, sectors: pd.Series) -> pd.Series:
        rate_sensitive = {s.upper() for s in self.cfg.rate_sensitive_sectors}
        defensive = {s.upper() for s in self.cfg.defensive_sectors}

        out = pd.Series(0.0, index=sectors.index, dtype=float)

        normalized = sectors.astype(str).str.upper().str.strip()
        out.loc[normalized.isin(rate_sensitive)] = 1.0
        out.loc[normalized.isin(defensive)] = -1.0

        return out

    def _neutral(self, index: pd.Index, columns: pd.Index) -> pd.DataFrame:
        return pd.DataFrame(self.cfg.neutral_value, index=index, columns=columns, dtype=float)

    @staticmethod
    def _first_existing(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None
