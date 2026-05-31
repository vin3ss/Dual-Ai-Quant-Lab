"""Alpha modules. Each produces a cross-sectional signal (higher = more attractive).

Every signal must be point-in-time: at date t it may only use data available by t.
"""
from .base import AlphaSignal

__all__ = ["AlphaSignal"]
