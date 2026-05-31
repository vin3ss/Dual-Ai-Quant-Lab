"""Generate the strategy's current target holdings + market trend + a chart.

    python -m scripts.generate_holdings [--top 15]

This turns the research engine into an actionable monthly output:
  - the stocks the momentum model favors right now (with weights),
  - the current market regime (risk-on / risk-off),
  - a chart of the market trend and the target book,
  - if you provide data_in/my_holdings.csv (symbol,weight), a BUY/SELL/HOLD diff.

NOT financial advice. This is the systematic model's output; the decision to act is
yours. It uses ONLY price/technical data — no fundamentals, no news, no sentiment
(those modules are inert without data).
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
from nse_alpha_forge.data import load_universe, LoaderConfig, MarketData
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.alpha.regime import RegimeDetector
from nse_alpha_forge.portfolio import PortfolioConstructor
from nse_alpha_forge.portfolio.universe import apply_liquidity_filter, apply_constituent_filter
from nse_alpha_forge.risk import RiskManager


def build_weights(data: MarketData, cfg: Config, constituents, top_liq=300):
    sig = MomentumSignal(12, 1).compute(data)
    has_sectors = bool((data.sectors.astype(str).str.upper() != "UNKNOWN").any())
    pc = PortfolioConstructor(StrategyConfig(sector_neutral=has_sectors))
    comp = pc.combine({"momentum": sig})
    if constituents is not None:
        comp = apply_constituent_filter(comp, constituents)
    else:
        comp = apply_liquidity_filter(comp, data.prices, data.volume, top_n=top_liq)
    w = pc.to_weights(comp, sectors=data.sectors)
    rm = RiskManager(cfg.risk)
    w = rm.apply_caps(w, data.sectors)
    w = rm.vol_target(w, data.returns())
    w = rm.apply_regime(w, RegimeDetector().detect(data))
    w = rm.capacity_aware_targets(
        target_weights=w, prices=data.prices, volume=data.volume,
        portfolio_value=cfg.cost.portfolio_value,
        max_adv_participation=cfg.cost.max_adv_participation, adv_window=cfg.cost.adv_window,
        candidate_scores=comp,
    )
    return w, RegimeDetector().detect(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data_in")
    ap.add_argument("--top", type=int, default=15)
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

    cons = pd.read_csv(dd / "constituents.csv") if (dd / "constituents.csv").exists() else None
    cfg = Config(); cfg.cost.execution_lag_bars = 1

    weights, regime = build_weights(data, cfg, cons)
    asof = weights.index[-1]
    book = weights.loc[asof]
    book = book[book.abs() > 1e-6].sort_values(ascending=False)

    # --- market trend / regime read ---
    proxy = (1 + data.returns().mean(axis=1).fillna(0)).cumprod()
    reg_now = float(regime.loc[asof])
    mom_12m = proxy.iloc[-1] / proxy.iloc[-13] - 1 if len(proxy) > 13 else float("nan")
    trend = "UPTREND" if proxy.iloc[-1] > proxy.rolling(6).mean().iloc[-1] else "DOWNTREND"
    risk = "RISK-ON (full exposure)" if reg_now >= 0.95 else \
           ("RISK-OFF (de-risked)" if reg_now < 0.6 else "CAUTIOUS (partial)")

    # --- chart ---
    fig, ax = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [2, 3]})
    ax[0].plot(proxy.index, proxy.values, color="#1f77b4", lw=1.6)
    risk_off = regime.reindex(proxy.index) < 0.6
    ax[0].fill_between(proxy.index, proxy.min(), proxy.max(), where=risk_off.values,
                       color="red", alpha=0.12, label="model risk-off")
    ax[0].set_title(f"NSE market trend (equal-weight proxy) — now: {trend}, {risk}")
    ax[0].legend(loc="upper left"); ax[0].grid(alpha=0.3)

    topn = book.head(args.top)[::-1]
    ax[1].barh([str(s) for s in topn.index], topn.values * 100, color="#2ca02c")
    ax[1].set_xlabel("target weight (%)")
    ax[1].set_title(f"Model target holdings as of {asof.date()} (top {args.top} of {len(book)})")
    ax[1].grid(alpha=0.3, axis="x")
    fig.tight_layout()
    out_png = Path("Reports") / "current_holdings.png"
    out_png.parent.mkdir(exist_ok=True)
    fig.savefig(out_png, dpi=110, bbox_inches="tight")

    # --- holdings diff vs your portfolio (optional) ---
    diff_txt = ""
    myh = dd / "my_holdings.csv"
    if myh.exists():
        cur = pd.read_csv(myh)
        cur.columns = [c.lower().strip() for c in cur.columns]
        held = set(cur["symbol"].astype(str).str.upper())
        target = set(book.index.astype(str))
        buys = sorted(target - held); sells = sorted(held - target); holds = sorted(held & target)
        diff_txt = (f"\nVs YOUR holdings:\n  HOLD : {', '.join(holds) or '-'}\n"
                    f"  BUY  : {', '.join(buys) or '-'}\n  SELL : {', '.join(sells) or '-'}\n")

    print("=" * 60)
    print(f" MODEL OUTPUT  (as of {asof.date()})")
    print("=" * 60)
    print(f"Market: {trend} | 12m proxy return {mom_12m:+.1%} | Model stance: {risk}")
    print(f"Universe: {'Nifty-500 (rigid)' if cons is not None else 'liquidity top-N'}, "
          f"{len(book)} positions")
    print(f"\nTop {args.top} target holdings (momentum/technical only):")
    for s, w in book.head(args.top).items():
        print(f"  {str(s):14} {w*100:5.1f}%")
    print(diff_txt)
    print("Chart: Reports/current_holdings.png")
    print("\nNOT financial advice. Momentum/technical only — NO fundamentals, news, or")
    print("sentiment (no data). Edge is modest (~0.5 Sharpe) and survivorship-uncertain.")


if __name__ == "__main__":
    main()
