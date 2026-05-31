"""Fetch split/bonus corporate actions for the liquid bhavcopy universe.

    python -m scripts.fetch_corporate_actions --top-n 500

Writes data_in/corporate_actions.csv in the format the loader's
`corporate_actions_path` expects: symbol, ex_date, factor, availability_date.
`factor` is the price-division ratio (Yahoo records a 1:1 bonus as a 2.0 split, a
5:1 split as 5.0, etc.), which is exactly what `_build_adjusted_close` divides by.

Apply it to the SURVIVORSHIP-FREE bhavcopy (not Yahoo prices):
    LoaderConfig(..., corporate_actions_path="data_in/corporate_actions.csv")
This adjusts splits/bonuses while keeping the full bhavcopy universe (dead names
included). Run locally (needs Yahoo).

COVERAGE NOTE: uses names Yahoo knows (mostly survivors + recently delisted). Dead
names that had splits won't be covered — a minor residual, since delistings are
usually price collapses, not splits. For full coverage, append NSE corporate-actions
rows in the same 4-column format.
"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import pandas as pd

from scripts.fetch_yahoo import pick_universe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=500)
    ap.add_argument("--bhavcopy-dir", default="data_in/bhavcopy")
    ap.add_argument("--out", default="data_in/corporate_actions.csv")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("pip install yfinance")

    tickers = pick_universe(Path(args.bhavcopy_dir), args.top_n)
    print(f"Fetching split/bonus history for {len(tickers)} tickers...")

    rows = []
    for i, t in enumerate(tickers):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                splits = yf.Ticker(f"{t}.NS").splits
        except Exception:
            continue
        if splits is None or len(splits) == 0:
            continue
        for dt, ratio in splits.items():
            if ratio and float(ratio) > 0:
                d = pd.Timestamp(dt).strftime("%Y-%m-%d")
                rows.append({"symbol": t, "ex_date": d, "factor": float(ratio),
                             "availability_date": d})
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(tickers)} scanned, {len(rows)} actions so far")
        time.sleep(0.05)

    df = pd.DataFrame(rows, columns=["symbol", "ex_date", "factor", "availability_date"])
    if not df.empty:
        df = df.sort_values(["symbol", "ex_date"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    n_sym = df["symbol"].nunique() if not df.empty else 0
    print(f"\nWrote {len(df)} corporate actions across {n_sym} symbols -> {args.out}")
    if not df.empty:
        print(df.head(12).to_string(index=False))
    print("\nNow re-run validation on the adjusted, survivorship-free bhavcopy:")
    print("  python -m scripts.run_real_validation   (uses data_in/corporate_actions.csv automatically)")


if __name__ == "__main__":
    main()
