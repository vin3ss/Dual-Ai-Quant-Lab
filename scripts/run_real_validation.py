"""Run the validation harness on real data dropped in ./data_in.

    python -m scripts.run_real_validation [--data-dir data_in] [--split 0.7]

Builds the full strategy (momentum [+quality] -> portfolio -> risk caps + vol target
+ regime gate [+ macro sector tilt]) and runs holdout, walk-forward, and regime-stress
validation. Writes a markdown report to Reports/.

This is the moment the project stops being theoretical: the numbers below are only as
honest as the data you feed it. Read the loader's DataQualityWarnings and PROJECT_STATE
issues #6-#17 before trusting anything.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from nse_alpha_forge.config import Config, StrategyConfig
from nse_alpha_forge.data import load_universe, LoaderConfig, MarketData
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.alpha.fundamental import QualitySignal
from nse_alpha_forge.alpha.regime import RegimeDetector
from nse_alpha_forge.alpha.macro import MacroSignal
from nse_alpha_forge.portfolio import PortfolioConstructor
from nse_alpha_forge.portfolio.universe import apply_liquidity_filter
from nse_alpha_forge.risk import RiskManager
from nse_alpha_forge.backtest import walk_forward, holdout_split, regime_stress


def _has_sectors(data: MarketData) -> bool:
    return bool((data.sectors.astype(str).str.upper() != "UNKNOWN").any())


def make_strategy(cfg: Config):
    """Return a weights_fn(data, params) closing over cfg."""

    def strategy_weights(data: MarketData, params: dict | None = None) -> pd.DataFrame:
        p = params or {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            signals = {
                "momentum": MomentumSignal(
                    lookback_months=p.get("mom_lookback", 12), skip_months=1
                ).compute(data)
            }
            if data.fundamentals:
                signals["quality"] = QualitySignal().compute(data)

            pc = PortfolioConstructor(StrategyConfig(sector_neutral=_has_sectors(data)))
            composite = pc.combine(signals)
            # Restrict to the point-in-time liquid universe (issue #19)
            composite = apply_liquidity_filter(
                composite, data.prices, data.volume,
                top_n=p.get("liq_top_n", 300), lookback=p.get("liq_lookback", 6),
            )
            weights = pc.to_weights(composite, sectors=data.sectors)

            rm = RiskManager(cfg.risk)
            weights = rm.apply_caps(weights, data.sectors)
            weights = rm.vol_target(weights, data.returns())
            weights = rm.apply_regime(weights, RegimeDetector().detect(data))

            if data.macro is not None:
                weights = pc.apply_sector_tilt(
                    weights, MacroSignal().compute(data), data.sectors,
                    strength=p.get("macro_strength", 0.25),
                )
        return weights

    return strategy_weights


def _load(data_dir: Path) -> MarketData:
    bhav = data_dir / "bhavcopy"
    if not bhav.exists() or not list(bhav.glob("*.csv")):
        raise SystemExit(
            f"No bhavcopy CSVs found in {bhav}. See data_in/README.md and "
            f"Research/Datasets/REAL_DATA_RUNBOOK.md."
        )
    opt = lambda name: (data_dir / name) if (data_dir / name).exists() else None
    cfg = LoaderConfig(
        source="csv",
        bhavcopy_dir=bhav,
        sectors_path=opt("sectors.csv"),
        fundamentals_path=opt("fundamentals.csv"),
        macro_path=opt("macro.csv"),
        corporate_actions_path=opt("corporate_actions.csv"),  # split/bonus adjustment (#18)
        use_cache=False,  # CA adjustment changes prices; don't serve a stale unadjusted cache
        resample="ME",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return load_universe("1990-01-01", "2100-01-01", config=cfg)


def _load_yahoo(ydir: Path) -> MarketData:
    px = pd.read_csv(ydir / "prices.csv", index_col=0, parse_dates=True).sort_index()
    vpath = ydir / "volume.csv"
    vol = (pd.read_csv(vpath, index_col=0, parse_dates=True).sort_index()
           if vpath.exists() else None)
    sectors = pd.Series("UNKNOWN", index=px.columns, name="sector")
    return MarketData(prices=px, sectors=sectors, volume=vol)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data_in")
    ap.add_argument("--split", type=float, default=0.7)
    ap.add_argument("--yahoo", action="store_true",
                    help="use adjusted data from data_in/yahoo instead of bhavcopy")
    args = ap.parse_args()

    cfg = Config()
    cfg.cost.execution_lag_bars = 1  # honest next-bar execution (no same-close look-ahead, #14)
    data = _load_yahoo(Path(args.data_dir) / "yahoo") if args.yahoo else _load(Path(args.data_dir))
    n = len(data.prices.index)
    strategy = make_strategy(cfg)

    lines = ["# Real-Data Validation Report", ""]
    lines.append(f"Universe: {data.prices.shape[1]} tickers, {n} monthly bars "
                 f"({data.prices.index.min().date()} to {data.prices.index.max().date()})")
    lines.append("")

    # 1. Holdout IS vs OOS
    ho = holdout_split(strategy, data, cfg, split=args.split)
    g = ho["overfitting_gap"]
    lines += [
        "## Holdout (IS vs OOS)",
        f"- IS Sharpe:  {g['is_sharpe']:.2f}",
        f"- OOS Sharpe: {g['oos_sharpe']:.2f}",
        f"- Degradation (IS-OOS): {g['sharpe_degradation']:.2f}   "
        f"{'⚠️ large — likely overfit' if g['sharpe_degradation'] > 0.5 else 'ok'}",
        f"- OOS CAGR: {ho['oos_stats']['cagr']:.2%}, OOS MaxDD: {ho['oos_stats']['max_dd']:.2%}",
        "",
    ]

    # 2. Walk-forward (adaptive windows to data length; lookback buffer for signals)
    train_w = min(36, max(12, n // 3))
    test_w = max(6, n // 8)
    if n >= train_w + test_w + 1:
        wf = walk_forward(strategy, data, cfg, train_window=train_w, test_window=test_w,
                          step=test_w, lookback=12)
        s = wf.stats
        lines += [
            f"## Walk-forward (train={train_w}m, test={test_w}m, {len(wf.windows)} windows)",
            f"- OOS Sharpe: {s['sharpe']:.2f}",
            f"- OOS CAGR: {s['cagr']:.2%}, Vol: {s['vol']:.2%}, MaxDD: {s['max_dd']:.2%}",
            "",
        ]
    else:
        lines += ["## Walk-forward", f"- Skipped: only {n} bars (need ≥ {train_w+test_w+1}).", ""]

    # 3. Regime stress over thirds of the sample
    idx = data.prices.index
    thirds = [idx[0], idx[n // 3], idx[2 * n // 3], idx[-1]]
    windows = {
        "first_third": (thirds[0], thirds[1]),
        "middle_third": (thirds[1], thirds[2]),
        "last_third": (thirds[2], thirds[3]),
    }
    rs = regime_stress(strategy, data, cfg, windows)
    lines += ["## Regime stress (sample thirds)", "```",
              rs[["cagr", "sharpe", "max_dd"]].round(3).to_string(), "```", ""]

    lines += [
        "## Caveats (do not skip)",
        "Numbers reflect the data quality you fed in. Still-unmodeled biases (PROJECT_STATE "
        "issues #14-#17): execution-price simultaneity, vol-target/capacity decoupling, 0% "
        "cash yield, and survivorship if the universe isn't point-in-time. Treat OOS Sharpe "
        "as an optimistic ceiling.",
    ]

    report = "\n".join(lines)
    out = Path("Reports") / "real_validation_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    print(report)
    print(f"\n[written to {out}]")


if __name__ == "__main__":
    main()
