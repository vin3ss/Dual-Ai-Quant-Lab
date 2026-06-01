"""Enrich the model's top-momentum names with CURRENT fundamentals + recent news/sentiment.

    python -m scripts.enrich_holdings --top 8

IMPORTANT honesty note:
- This is a LIVE screen using TODAY's data for TODAY's decision — NOT part of the
  backtest. Using current fundamentals/news for a current choice is legitimate (no
  look-ahead). It is NOT point-in-time history, so it must never be fed into the backtest.
- Fundamentals/news come from Yahoo (yfinance); coverage is imperfect for some NSE names.
- Sentiment is a crude keyword polarity on headlines — a rough flag, not a real NLP model.
- NOT financial advice.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from nse_alpha_forge.data import load_universe, LoaderConfig
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.portfolio.universe import apply_constituent_filter
from nse_alpha_forge.analytics import volume_spike, money_flow

POS = {"surge", "profit", "gain", "gains", "beat", "beats", "upgrade", "record", "strong",
       "rise", "rises", "jump", "growth", "win", "wins", "bullish", "high", "rally", "soar"}
NEG = {"fall", "falls", "loss", "drop", "drops", "fraud", "probe", "downgrade", "weak",
       "decline", "cut", "cuts", "slump", "plunge", "bearish", "lawsuit", "default", "fine", "raid"}


def sentiment(headlines: list[str]) -> str:
    text = " ".join(headlines).lower()
    p = sum(text.count(w) for w in POS)
    n = sum(text.count(w) for w in NEG)
    if not headlines:
        return "no news"
    if p > n:
        return f"positive (+{p}/-{n})"
    if n > p:
        return f"negative (+{p}/-{n})"
    return f"neutral (+{p}/-{n})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--data-dir", default="data_in")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("pip install yfinance")

    dd = Path(args.data_dir)
    opt = lambda n: (dd / n) if (dd / n).exists() else None
    lc = LoaderConfig(source="csv", bhavcopy_dir=dd / "bhavcopy",
                      corporate_actions_path=opt("corporate_actions.csv"),
                      sectors_path=opt("sectors.csv"), use_cache=False, resample="ME")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = load_universe("2019-01-01", "2100-01-01", config=lc)

    sig = MomentumSignal(12, 1).compute(data)
    cons = pd.read_csv(dd / "constituents.csv") if (dd / "constituents.csv").exists() else None
    if cons is not None:
        sig = apply_constituent_filter(sig, cons)
    latest = sig.iloc[-1].dropna().sort_values(ascending=False)
    top = list(latest.head(args.top).index)

    # Smart-money proxies from our own bhavcopy volume (free, no yfinance needed)
    vspk = volume_spike(data.prices, data.volume).iloc[-1]
    mflow = money_flow(data.prices, data.volume).iloc[-1]

    print(f"Top {args.top} momentum names as of {sig.index[-1].date()} "
          f"(strongest 12-1 momentum):\n")
    print(f"{'SYMBOL':12}{'Mom z':>7}{'Flow':>6}{'VolX':>6}{'P/E':>7}{'ROE%':>7}{'D/E':>7}  Sentiment")
    print("-" * 80)

    for sym in top:
        momz = latest[sym]
        sm_flow = mflow.get(sym, float("nan"))
        sm_vol = vspk.get(sym, float("nan"))
        pe = roe = mgn = de = float("nan")
        sent = "n/a"; heads = []
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                t = yf.Ticker(f"{sym}.NS")
                info = t.info or {}
                pe = info.get("trailingPE", float("nan"))
                roe = (info.get("returnOnEquity") or float("nan"))
                roe = roe * 100 if pd.notna(roe) else float("nan")
                mgn = (info.get("profitMargins") or float("nan"))
                mgn = mgn * 100 if pd.notna(mgn) else float("nan")
                de = info.get("debtToEquity", float("nan"))
                news = t.news or []
                heads = [(n.get("content", {}).get("title") or n.get("title") or "")
                         for n in news[:4]]
                heads = [h for h in heads if h]
                sent = sentiment(heads)
        except Exception:
            pass

        def f(x, d=1):
            return f"{x:.{d}f}" if pd.notna(x) else "  -"
        print(f"{sym:12}{momz:7.2f}{f(sm_flow,2):>6}{f(sm_vol):>6}"
              f"{f(pe):>7}{f(roe):>7}{f(de):>7}  {sent}")
        for h in heads[:2]:
            print(f"            • {h[:78]}")

    print("\nColumns: Mom z = momentum strength | Flow = money-flow [-1..1] (accumulation>0) |")
    print("VolX = volume vs trailing median (>1.5 elevated) | P/E,ROE,D/E,Sentiment = live Yahoo.")
    print("Flow/VolX are from our own bhavcopy (free). Richer smart-money (FII/DII, bulk/block")
    print("deals, delivery%, F&O OI) need separate free NSE files — not yet ingested.")
    print("LIVE snapshot for TODAY's decision; NOT in the backtest; NOT financial advice.")


if __name__ == "__main__":
    main()
