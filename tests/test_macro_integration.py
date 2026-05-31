"""Issue #10 fix: macro applied as a sector-budget overlay, not a demeaned score."""

import numpy as np
import pandas as pd

from nse_alpha_forge.config import StrategyConfig
from nse_alpha_forge.portfolio import PortfolioConstructor
from nse_alpha_forge.alpha.base import AlphaSignal


def _setup():
    dates = pd.date_range("2024-01-31", periods=2, freq="ME")
    tickers = ["BANK1", "BANK2", "FMCG1", "FMCG2"]
    sectors = pd.Series(
        {"BANK1": "BANK", "BANK2": "BANK", "FMCG1": "FMCG", "FMCG2": "FMCG"},
        name="sector",
    )
    weights = pd.DataFrame(0.25, index=dates, columns=tickers)   # gross 1.0, sector-balanced
    # macro favors BANK (+0.5), penalizes FMCG (-0.5) — uniform within sector
    macro = pd.DataFrame(
        {"BANK1": 0.5, "BANK2": 0.5, "FMCG1": -0.5, "FMCG2": -0.5},
        index=dates,
    )
    return weights, macro, sectors


def test_sector_tilt_shifts_budget_and_preserves_gross():
    weights, macro, sectors = _setup()
    pc = PortfolioConstructor(StrategyConfig())

    tilted = pc.apply_sector_tilt(weights, macro, sectors, strength=0.5)
    dt = weights.index[0]

    bank = tilted.loc[dt, ["BANK1", "BANK2"]].sum()
    fmcg = tilted.loc[dt, ["FMCG1", "FMCG2"]].sum()

    assert bank > 0.5 > fmcg                       # favored sector gets more budget
    assert abs(tilted.loc[dt].abs().sum() - 1.0) < 1e-9   # gross preserved
    # within-sector relative weights unchanged (the stock picks are untouched)
    assert np.isclose(tilted.loc[dt, "BANK1"], tilted.loc[dt, "BANK2"])


def test_sector_tilt_survives_where_blending_would_not():
    """Contrast: blending macro into the composite then sector-neutralizing zeroes
    it, but apply_sector_tilt produces a real, non-uniform sector budget."""
    weights, macro, sectors = _setup()
    pc = PortfolioConstructor(StrategyConfig())

    # blending path: sector-neutralize the macro score -> all zeros (the bug)
    neutralized = AlphaSignal.sector_neutralize(macro, sectors)
    assert (neutralized.abs() < 1e-9).all().all()

    # overlay path: real effect
    tilted = pc.apply_sector_tilt(weights, macro, sectors, strength=0.5)
    dt = weights.index[0]
    assert tilted.loc[dt, ["BANK1", "BANK2"]].sum() != tilted.loc[dt, ["FMCG1", "FMCG2"]].sum()


def test_sector_tilt_noop_when_macro_none_or_zero():
    weights, _, sectors = _setup()
    pc = PortfolioConstructor(StrategyConfig())

    assert pc.apply_sector_tilt(weights, None, sectors).equals(weights)

    zero = pd.DataFrame(0.0, index=weights.index, columns=weights.columns)
    pd.testing.assert_frame_equal(pc.apply_sector_tilt(weights, zero, sectors), weights)
