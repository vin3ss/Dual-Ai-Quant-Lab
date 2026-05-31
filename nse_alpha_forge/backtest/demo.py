"""End-to-end demo on synthetic data. No API keys or market data required.

    python -m nse_alpha_forge.backtest.demo

Wires: synthetic data -> momentum + quality signals -> portfolio -> risk caps
-> backtest. Numbers are illustrative of the *plumbing*, not a real edge.
"""

from __future__ import annotations

from ..config import DEFAULT
from ..data import make_synthetic_data
from ..alpha.technical import MomentumSignal
from ..alpha.fundamental import QualitySignal
from ..alpha.regime import RegimeDetector
from ..portfolio import PortfolioConstructor
from ..risk import RiskManager
from ..backtest import Backtester


def main() -> None:
    cfg = DEFAULT
    data = make_synthetic_data()

    signals = {
        "momentum": MomentumSignal(lookback_months=cfg.strategy.momentum_lookback_months,
                                   skip_months=cfg.strategy.momentum_skip_months).compute(data),
        "quality": QualitySignal().compute(data),
    }

    pc = PortfolioConstructor(cfg.strategy)
    composite = pc.combine(signals, weights={"momentum": 0.6, "quality": 0.4})
    weights = pc.to_weights(composite, sectors=data.sectors)

    rm = RiskManager(cfg.risk)
    weights = rm.apply_caps(weights, data.sectors)
    weights = rm.vol_target(weights, data.returns())

    # Regime gate: scale exposure down in unfavorable market states
    regime = RegimeDetector().detect(data)
    weights = rm.apply_regime(weights, regime)

    result = Backtester(cfg).run(weights, data.returns())

    print("=" * 44)
    print(" NSE Alpha Forge — demo backtest (synthetic)")
    print("=" * 44)
    print(result.summary())
    print("\nNote: synthetic data; numbers show the pipeline runs, not real alpha.")


if __name__ == "__main__":
    main()
