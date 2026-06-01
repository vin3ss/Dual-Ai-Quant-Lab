"""Paper-money portfolio simulation — start with virtual capital, 'invest' in the
strategy, and see the account curve vs just holding the market.

    python -m scripts.paper_portfolio --capital 100000 --start 2019-01-31

HONEST: this is a HYPOTHETICAL backtest on past data (survivorship-optimistic, modest
~0.4-0.7 Sharpe edge). It includes realistic costs, next-bar execution, and cash yield.
Past results do NOT predict future profit. Not financial advice. No real money.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nse_alpha_forge.config import Config, StrategyConfig
from nse_alpha_forge.data import load_universe, LoaderConfig
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.alpha.regime import RegimeDetector
from nse_alpha_forge.portfolio import PortfolioConstructor
from nse_alpha_forge.portfolio.universe import apply_constituent_filter, apply_liquidity_filter
from nse_alpha_forge.risk import RiskManager
from nse_alpha_forge.backtest import Backtester


def _maxdd(equity: pd.Series) -> float:
    return float((1 - equity / equity.cummax()).max())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--start", default="2019-01-31")
    ap.add_argument("--data-dir", default="data_in")
    args = ap.parse_args()

    dd = Path(args.data_dir)
    opt = lambda n: (dd / n) if (dd / n).exists() else None
    lc = LoaderConfig(source="csv", bhavcopy_dir=dd / "bhavcopy",
                      sectors_path=opt("sectors.csv"),
                      corporate_actions_path=opt("corporate_actions.csv"),
                      use_cache=False, resample="ME")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = load_universe("2019-01-01", "2100-01-01", config=lc)

    cfg = Config(); cfg.cost.execution_lag_bars = 1
    cons = pd.read_csv(dd / "constituents.csv") if (dd / "constituents.csv").exists() else None

    sig = MomentumSignal(12, 1).compute(data)
    pc = PortfolioConstructor(StrategyConfig(
        sector_neutral=bool((data.sectors.astype(str).str.upper() != "UNKNOWN").any())))
    comp = pc.combine({"momentum": sig})
    comp = apply_constituent_filter(comp, cons) if cons is not None else \
        apply_liquidity_filter(comp, data.prices, data.volume, top_n=300)
    w = pc.to_weights(comp, sectors=data.sectors)
    rm = RiskManager(cfg.risk)
    w = rm.apply_caps(w, data.sectors); w = rm.vol_target(w, data.returns())
    w = rm.apply_regime(w, RegimeDetector().detect(data))
    w = rm.capacity_aware_targets(target_weights=w, prices=data.prices, volume=data.volume,
                                  portfolio_value=cfg.cost.portfolio_value,
                                  max_adv_participation=cfg.cost.max_adv_participation,
                                  candidate_scores=comp, adv_window=cfg.cost.adv_window)

    res = Backtester(cfg).run(w, data.returns(), prices=data.prices, volume=data.volume)
    start = pd.Timestamp(args.start)
    rets = res.returns[res.returns.index >= start]
    mkt_ret = data.returns().mean(axis=1).fillna(0)
    mkt_ret = mkt_ret[mkt_ret.index >= start]

    eq = args.capital * (1 + rets).cumprod()
    mkt = args.capital * (1 + mkt_ret).cumprod()
    n = len(eq); yrs = n / 12.0
    cagr = (eq.iloc[-1] / args.capital) ** (1 / yrs) - 1 if yrs > 0 else 0
    mkt_cagr = (mkt.iloc[-1] / args.capital) ** (1 / yrs) - 1 if yrs > 0 else 0

    print("=" * 64)
    print(f" PAPER PORTFOLIO  —  start ₹{args.capital:,.0f} on {eq.index[0].date()}")
    print("=" * 64)
    print(f" STRATEGY  final ₹{eq.iloc[-1]:,.0f}  ({eq.iloc[-1]/args.capital-1:+.1%} total, "
          f"{cagr:+.1%}/yr, maxDD {_maxdd(eq):.1%})")
    print(f" MARKET    final ₹{mkt.iloc[-1]:,.0f}  ({mkt.iloc[-1]/args.capital-1:+.1%} total, "
          f"{mkt_cagr:+.1%}/yr, maxDD {_maxdd(mkt):.1%})")
    edge = eq.iloc[-1] - mkt.iloc[-1]
    print(f" Strategy vs market: ₹{edge:+,.0f}  ->  "
          f"{'beat' if edge>0 else 'LAGGED'} buy-and-hold")
    # last 12 months
    if n > 12:
        r12 = eq.iloc[-1] / eq.iloc[-13] - 1
        print(f" Last 12 months: {r12:+.1%}  (momentum has been in drawdown)")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(eq.index, eq.values, label="Strategy (paper)", color="#1a7f37", lw=1.8)
    ax.plot(mkt.index, mkt.values, label="Market (equal-weight, buy & hold)", color="#57606a", lw=1.4, ls="--")
    ax.axhline(args.capital, color="#cccccc", lw=0.8)
    ax.set_title(f"₹{args.capital:,.0f} paper portfolio — strategy vs market (HYPOTHETICAL)")
    ax.set_ylabel("₹ account value"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    out = Path("Reports") / "paper_portfolio.png"; out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"\n Chart: {out}")
    print(" HYPOTHETICAL backtest on past, survivorship-optimistic data. Past ≠ future.")
    print(" Not a prediction, not financial advice.")


if __name__ == "__main__":
    main()
