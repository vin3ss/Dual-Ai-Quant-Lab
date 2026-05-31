"""Fetch split/dividend-adjusted monthly prices from Yahoo for the liquid NSE universe.

    python -m scripts.fetch_yahoo --top-n 150 --start 2019-01-01 --end 2026-05-31

Picks the top-N most-traded names from data_in/bhavcopy (by median turnover),
downloads adjusted close + volume from Yahoo (ticker + .NS), and writes
data_in/yahoo/{prices,volume}.csv. Then:

    python -m scripts.run_real_validation --yahoo

Caveat: Yahoo India data has gaps/bad ticks and MISSES delisted names (so it is
survivorship-biased), but it IS corporate-action adjusted — the point here is a fair
re-test of momentum without fake split/bonus returns.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd


def pick_universe(bhav_dir: Path, top_n: int) -> list[str]:
    from nse_alpha_forge.data import load_universe, LoaderConfig
    cfg = LoaderConfig(source="csv", bhavcopy_dir=bhav_dir, use_cache=False, resample="ME")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = load_universe("1990-01-01", "2100-01-01", config=cfg)
    if d.volume is None:
        return list(d.prices.columns[:top_n])
    turnover = (d.prices * d.volume)
    median_turnover = turnover.median(axis=0).sort_values(ascending=False)
    return list(median_turnover.head(top_n).index)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2026-05-31")
    ap.add_argument("--top-n", type=int, default=150)
    ap.add_argument("--bhavcopy-dir", default="data_in/bhavcopy")
    ap.add_argument("--out", default="data_in/yahoo")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("pip install yfinance")

    tickers = pick_universe(Path(args.bhavcopy_dir), args.top_n)
    ynames = [f"{t}.NS" for t in tickers]
    print(f"Downloading {len(ynames)} adjusted monthly series from Yahoo...")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.download(ynames, start=args.start, end=args.end, interval="1mo",
                         auto_adjust=True, progress=False, threads=True)

    close = df["Close"].copy()
    vol = df["Volume"].copy()
    strip = lambda cols: [c[:-3] if str(c).endswith(".NS") else c for c in cols]
    close.columns = strip(close.columns)
    vol.columns = strip(vol.columns)
    close = close.dropna(how="all")
    vol = vol.reindex(close.index)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    close.to_csv(out / "prices.csv")
    vol.to_csv(out / "volume.csv")
    print(f"Wrote prices {close.shape} and volume to {out}/. Now run:")
    print("  python -m scripts.run_real_validation --yahoo")


if __name__ == "__main__":
    main()
