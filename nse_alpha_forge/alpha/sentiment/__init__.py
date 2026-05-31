"""Sentiment alpha — news & earnings-call NLP scores.

This module does NOT call an LLM or scrape news. It consumes a prepared
date x ticker sentiment panel in `data.news`.

Ingestion boundary:
- Earnings-call/news parsing belongs upstream.
- `data.news` must be indexed by publication/availability timestamp, not by
  fiscal period or event date.
- Higher score = more positive sentiment = more attractive.

Point-in-time:
All inputs are lagged one bar before scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd

from ..base import AlphaSignal


class SentimentDataWarning(RuntimeWarning):
    """Sentiment data missing or potentially biased."""


@dataclass(frozen=True)
class SentimentConfig:
    winsor_limits: float = 0.02
    max_abs_score: float = 3.0
    neutral_value: float = 0.0


class SentimentSignal(AlphaSignal):
    name = "sentiment"

    def __init__(self, cfg: SentimentConfig | None = None):
        self.cfg = cfg or SentimentConfig()

    def compute(self, data) -> pd.DataFrame:
        prices = data.prices
        news = getattr(data, "news", None)

        if news is None or not isinstance(news, pd.DataFrame) or news.empty:
            warnings.warn(
                "SentimentSignal: data.news is absent; returning neutral sentiment.",
                SentimentDataWarning,
                stacklevel=2,
            )
            return self._neutral(prices.index, prices.columns)

        panel = self._prepare_panel(news, prices.index, prices.columns)

        # Strict point-in-time: signal at t uses sentiment available before t.
        lagged = panel.shift(1)

        scored = self.zscore(lagged)
        scored = self.winsorize(scored, limits=self.cfg.winsor_limits)
        scored = scored.clip(-self.cfg.max_abs_score, self.cfg.max_abs_score)

        return scored.fillna(self.cfg.neutral_value)

    def _prepare_panel(
        self,
        news: pd.DataFrame,
        index: pd.Index,
        columns: pd.Index,
    ) -> pd.DataFrame:
        frame = news.copy()

        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.set_index("date")

        if not isinstance(frame.index, pd.DatetimeIndex):
            raise TypeError("data.news must have a DatetimeIndex or a date column.")

        frame.columns = [str(c).upper().strip() for c in frame.columns]

        return (
            frame.sort_index()
            .reindex(index=index, columns=columns)
            .astype(float)
        )

    def _neutral(self, index: pd.Index, columns: pd.Index) -> pd.DataFrame:
        return pd.DataFrame(
            self.cfg.neutral_value,
            index=index,
            columns=columns,
            dtype=float,
        )
