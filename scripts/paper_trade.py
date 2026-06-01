"""Forward paper-trading journal — the 'brain' that learns whether the radar works.

    python -m scripts.paper_trade --snapshot        # log today's calls
    python -m scripts.paper_trade --review          # grade past calls vs what happened

It records the radar's DATA-ONLY verdict (momentum + delivery + money-flow — all
point-in-time, no look-ahead from live fundamentals/news) for the top names at a date,
into data_in/journal/picks.csv. Later, --review fetches forward returns and reports:
  - did WATCH names go up?  (hit rate, avg return)
  - did WATCH BEAT AVOID and the market?  <- the only question that matters

No money at risk. This is how you find out if the radar has real forward signal before
trusting it. Not financial advice.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from nse_alpha_forge.config import StrategyConfig
from nse_alpha_forge.data import load_universe, LoaderConfig
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.portfolio.universe import apply_constituent_filter
from nse_alpha_forge.analytics import money_flow

JOURNAL = Path("data_in/journal/picks.csv")


def data_verdict(momz, flow, dlv) -> str:
    """Point-in-time, data-only confluence (no live fundamentals/news, so reconstructable
    at any past date for an honest forward test)."""
    if pd.notna(flow) and flow <= -0.5:
        return "AVOID"                       # heavy distribution
    if momz >= 0.3 and (pd.notna(dlv) and dlv >= 45) and (pd.notna(flow) and flow >= 0):
        return "WATCH"                       # momentum + delivery conviction + accumulation
    if momz >= 0.3:
        return "CAUTION"
    return "NEUTRAL"


def _load():
    dd = Path("data_in")
    opt = lambda n: (dd / n) if (dd / n).exists() else None
    lc = LoaderConfig(source="csv", bhavcopy_dir=dd / "bhavcopy",
                      corporate_actions_path=opt("corporate_actions.csv"),
                      sectors_path=opt("sectors.csv"), use_cache=False, resample="ME")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = load_universe("2019-01-01", "2100-01-01", config=lc)
    cons = pd.read_csv(dd / "constituents.csv") if (dd / "constituents.csv").exists() else None
    deliv = None
    if (dd / "smartmoney" / "delivery.csv").exists():
        dv = pd.read_csv(dd / "smartmoney" / "delivery.csv")
        dv["deliv_pct"] = pd.to_numeric(dv["deliv_pct"], errors="coerce")
        dv["symbol"] = dv["symbol"].astype(str).str.upper().str.strip()
        dv["date"] = pd.to_datetime(dv["date"])
        deliv = dv.pivot_table(index="date", columns="symbol", values="deliv_pct", aggfunc="last")
    return data, cons, deliv


def snapshot(asof_str, top):
    data, cons, deliv = _load()
    sig = MomentumSignal(12, 1).compute(data)
    if cons is not None:
        sig = apply_constituent_filter(sig, cons)
    flow = money_flow(data.prices, data.volume)

    idx = sig.index
    asof = pd.Timestamp(asof_str) if asof_str else idx[-1]
    asof = idx[idx <= asof][-1]              # snap to an available bar

    momrow = sig.loc[asof].dropna().sort_values(ascending=False)
    names = list(momrow.head(top).index)
    flowrow = flow.loc[asof]
    delivrow = deliv.reindex(index=[asof]).iloc[0] if deliv is not None else pd.Series(dtype=float)

    rows = []
    for s in names:
        momz = momrow[s]; fl = flowrow.get(s, float("nan")); dl = delivrow.get(s, float("nan"))
        rows.append({"snapshot_date": asof.date().isoformat(), "symbol": s,
                     "verdict": data_verdict(momz, fl, dl),
                     "entry_price": round(float(data.prices.loc[asof, s]), 2),
                     "mom": round(float(momz), 2),
                     "flow": round(float(fl), 2) if pd.notna(fl) else "",
                     "dlv": round(float(dl), 1) if pd.notna(dl) else ""})
    new = pd.DataFrame(rows)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    if JOURNAL.exists():
        old = pd.read_csv(JOURNAL)
        new = pd.concat([old, new], ignore_index=True).drop_duplicates(
            ["snapshot_date", "symbol"], keep="last")
    new.to_csv(JOURNAL, index=False)
    vc = pd.Series([r["verdict"] for r in rows]).value_counts().to_dict()
    print(f"Logged {len(rows)} picks as of {asof.date()} -> {JOURNAL}")
    print(f"Verdict mix: {vc}")
    print("Re-fetch data next month, then: python -m scripts.paper_trade --review")


def review():
    if not JOURNAL.exists():
        raise SystemExit("No journal yet. Run --snapshot first.")
    data, _, _ = _load()
    px = data.prices
    latest = px.index[-1]
    proxy = (1 + data.returns().mean(axis=1).fillna(0)).cumprod()

    j = pd.read_csv(JOURNAL)
    j["snapshot_date"] = pd.to_datetime(j["snapshot_date"])
    idx = px.index
    fwd = []
    for _, r in j.iterrows():
        sym, d0 = r["symbol"], r["snapshot_date"]
        if sym not in px.columns or d0 not in idx or not r["entry_price"]:
            continue
        after = idx[idx > d0]
        if len(after) == 0:
            continue
        d1 = after[0]                         # fixed 1-bar (≈1-month) forward, equal horizon
        now = px.loc[d1, sym]
        if pd.isna(now):
            continue
        ret = now / float(r["entry_price"]) - 1
        mkt = proxy.loc[d1] / proxy.loc[d0] - 1
        fwd.append({"verdict": r["verdict"], "ret": ret, "excess": ret - mkt})
    if not fwd:
        print("No matured picks yet — re-fetch newer data (next month) and review again.")
        return
    f = pd.DataFrame(fwd)
    print("=" * 60)
    print(" PAPER-TRADING REVIEW — forward returns of logged calls")
    print("=" * 60)
    g = f.groupby("verdict")["ret"].agg(["count", "mean"]).reindex(["WATCH", "CAUTION", "NEUTRAL", "AVOID"]).dropna()
    for v, row in g.iterrows():
        hit = (f[f.verdict == v]["ret"] > 0).mean()
        print(f"  {v:8} n={int(row['count']):3}  avg fwd ret {row['mean']:+.2%}  hit-rate {hit:.0%}")
    w = f[f.verdict == "WATCH"]["ret"].mean() if (f.verdict == "WATCH").any() else float("nan")
    a = f[f.verdict == "AVOID"]["ret"].mean() if (f.verdict == "AVOID").any() else float("nan")
    print(f"\n  WATCH avg excess-vs-market: {f[f.verdict=='WATCH']['excess'].mean():+.2%}"
          if (f.verdict == 'WATCH').any() else "")
    if pd.notna(w) and pd.notna(a):
        verdict = "WATCH beat AVOID ✓ (signal)" if w > a else "WATCH did NOT beat AVOID ✗ (no signal yet)"
        print(f"  WATCH {w:+.2%} vs AVOID {a:+.2%}  ->  {verdict}")
    print("\n  n is tiny — one or two months proves nothing. The point is to accumulate")
    print("  months of honest, no-money data before ever risking capital.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--asof", default=None, help="snapshot as of this date (default latest)")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    if args.snapshot:
        snapshot(args.asof, args.top)
    elif args.review:
        review()
    else:
        ap.error("use --snapshot or --review")


if __name__ == "__main__":
    main()
