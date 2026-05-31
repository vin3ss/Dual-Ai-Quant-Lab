"""Sentiment alpha — news & earnings-call NLP signals.

INTERFACE STUB. Fill in compute(). Suggested approach: run earnings-call
transcripts through an LLM (see Research/PromptLibrary prompt A3) to extract a
management-confidence score and guidance-change score, lagged to the call date.
"""
from __future__ import annotations
import pandas as pd
from ..base import AlphaSignal


class SentimentSignal(AlphaSignal):
    name = "sentiment"

    def compute(self, data) -> pd.DataFrame:
        raise NotImplementedError(
            "Implement sentiment signal: parse data.news / data.transcripts into a "
            "date x ticker score, lagged to publication/call date. See prompt A3."
        )
