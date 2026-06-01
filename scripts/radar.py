"""NSE Smart Money Radar — one-command decision-support report.

    python -m scripts.radar [--top 12]

Combines: momentum + market regime + delivery conviction + money-flow + volume +
bulk/block deals + (live) fundamentals & news, into a per-stock read:
WATCH / CAUTION / AVOID — based on CONFLUENCE, never one column.

Prints a table and writes Reports/radar.html (open it in a browser).
DECISION-SUPPORT ONLY — not auto-trading, not validated alpha, not financial advice.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd

from nse_alpha_forge.config import Config, StrategyConfig
from nse_alpha_forge.data import load_universe, LoaderConfig
from nse_alpha_forge.alpha.technical import MomentumSignal
from nse_alpha_forge.alpha.regime import RegimeDetector
from nse_alpha_forge.portfolio.universe import apply_constituent_filter
from nse_alpha_forge.analytics import volume_spike, money_flow


def _verdict(momz, flow, dlv, deal, pe, news):
    """Confluence-based read. Green = aligned bullish evidence; red = warning."""
    green = sum([
        momz >= 0.3,
        pd.notna(dlv) and dlv >= 40,          # real delivery conviction
        pd.notna(flow) and flow >= 0,         # accumulation, not distribution
        pd.notna(pe) and 0 < pe <= 40,        # not wildly expensive
        news == "positive",
        deal == "BUY",
    ])
    red = sum([
        pd.notna(flow) and flow <= -0.5,      # heavy distribution
        pd.notna(pe) and pe > 60,             # very expensive
        news == "negative",
        deal == "SELL",
    ])
    if red >= 2:
        return "AVOID", green, red
    if red == 1:
        return "CAUTION", green, red
    if green >= 4:
        return "WATCH", green, red
    return "NEUTRAL", green, red


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data_in")
    ap.add_argument("--top", type=int, default=12)
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

    sig = MomentumSignal(12, 1).compute(data)
    cons = pd.read_csv(dd / "constituents.csv") if (dd / "constituents.csv").exists() else None
    if cons is not None:
        sig = apply_constituent_filter(sig, cons)
    asof = sig.index[-1]
    top = list(sig.iloc[-1].dropna().sort_values(ascending=False).head(args.top).index)

    vspk = volume_spike(data.prices, data.volume).iloc[-1]
    mflow = money_flow(data.prices, data.volume).iloc[-1]
    regime = RegimeDetector().detect(data)
    proxy = (1 + data.returns().mean(axis=1).fillna(0)).cumprod()
    reg_now = float(regime.loc[asof])
    stance = "RISK-ON" if reg_now >= 0.95 else ("RISK-OFF" if reg_now < 0.6 else "CAUTIOUS")
    mkt12 = proxy.iloc[-1] / proxy.iloc[-13] - 1 if len(proxy) > 13 else float("nan")

    # big-fish files
    sm = dd / "smartmoney"
    deliv = {}
    if (sm / "delivery.csv").exists():
        dv = pd.read_csv(sm / "delivery.csv")
        dv["deliv_pct"] = pd.to_numeric(dv["deliv_pct"], errors="coerce")
        dv["symbol"] = dv["symbol"].astype(str).str.upper().str.strip()
        deliv = dv.pivot_table(index="date", columns="symbol", values="deliv_pct",
                               aggfunc="last").iloc[-1].to_dict()
    deals = {}
    frames = [pd.read_csv(sm / f) for f in ("bulk_deals.csv", "block_deals.csv")
              if (sm / f).exists()]
    if frames:
        dl = pd.concat(frames, ignore_index=True); dl.columns = [c.lower().strip() for c in dl.columns]
        dl["symbol"] = dl["symbol"].astype(str).str.upper().str.strip()
        s = dl["action"].astype(str).str.upper().str.startswith("B").map({True: 1, False: -1})
        deals = (s * pd.to_numeric(dl["quantity"], errors="coerce")).groupby(dl["symbol"]).sum().to_dict()

    try:
        import yfinance as yf
    except ImportError:
        yf = None

    POS = {"surge", "profit", "gain", "beat", "record", "strong", "growth", "wins", "rally", "high"}
    NEG = {"fall", "loss", "fraud", "probe", "downgrade", "weak", "cut", "slump", "default", "lawsuit"}

    rows = []
    for sym in top:
        pe = roe = float("nan"); news = "n/a"; heads = []
        if yf is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    t = yf.Ticker(f"{sym}.NS"); info = t.info or {}
                    pe = info.get("trailingPE", float("nan"))
                    roe = (info.get("returnOnEquity") or float("nan"))
                    roe = roe * 100 if pd.notna(roe) else float("nan")
                    heads = [(n.get("content", {}).get("title") or n.get("title") or "")
                             for n in (t.news or [])[:4]]
                    heads = [h for h in heads if h]
                    txt = " ".join(heads).lower()
                    p, n = sum(txt.count(w) for w in POS), sum(txt.count(w) for w in NEG)
                    news = "positive" if p > n else ("negative" if n > p else "neutral") if heads else "n/a"
            except Exception:
                pass
        net = deals.get(sym)
        deal = "BUY" if (net and net > 0) else ("SELL" if (net and net < 0) else "-")
        momz, flow, vx, dlv = sig.iloc[-1][sym], mflow.get(sym, float("nan")), \
            vspk.get(sym, float("nan")), deliv.get(sym, float("nan"))
        verdict, g, r = _verdict(momz, flow, dlv, deal, pe, news)
        rows.append(dict(symbol=sym, mom=momz, flow=flow, volx=vx, dlv=dlv, deal=deal,
                         pe=pe, roe=roe, news=news, verdict=verdict, heads=heads))

    # --- console ---
    print("=" * 78)
    print(f" NSE SMART MONEY RADAR  —  as of {asof.date()}")
    print("=" * 78)
    print(f" Market: {stance}  (regime mult {reg_now:.2f}, 12m proxy {mkt12:+.1%})")
    uni = "Nifty-500 (rigid)" if cons is not None else "liquidity top-N"
    print(f" Universe: {uni} | showing top {args.top} momentum names\n")
    print(f"{'SYMBOL':12}{'Mom':>5}{'Flow':>6}{'VolX':>5}{'Dlv%':>6}{'Deal':>5}"
          f"{'P/E':>6}{'ROE':>6}  {'News':<9} VERDICT")
    print("-" * 78)
    for x in rows:
        def f(v, d=1):
            return f"{v:.{d}f}" if pd.notna(v) else "-"
        print(f"{x['symbol']:12}{x['mom']:5.2f}{f(x['flow'],2):>6}{f(x['volx']):>5}"
              f"{f(x['dlv']):>6}{x['deal']:>5}{f(x['pe']):>6}{f(x['roe']):>6}  "
              f"{x['news']:<9} {x['verdict']}")
    print("\nRULE: confluence, not one column. WATCH = momentum + delivery + flow + value +")
    print("clean news align. CAUTION/AVOID = warning flags. Decision-support, NOT auto-trading,")
    print("NOT validated alpha, NOT financial advice. Verify before acting.")

    _write_html(rows, asof, stance, reg_now, mkt12, uni, args.top)
    print(f"\nDashboard: Reports/radar.html")


def _write_html(rows, asof, stance, reg, mkt12, uni, top):
    color = {"WATCH": "#1a7f37", "CAUTION": "#9a6700", "AVOID": "#cf222e", "NEUTRAL": "#57606a"}
    def cell(v, d=1):
        return f"{v:.{d}f}" if pd.notna(v) else "-"
    trs = ""
    for x in rows:
        trs += (f"<tr><td><b>{x['symbol']}</b></td><td>{x['mom']:.2f}</td>"
                f"<td>{cell(x['flow'],2)}</td><td>{cell(x['volx'])}</td>"
                f"<td>{cell(x['dlv'])}</td><td>{x['deal']}</td>"
                f"<td>{cell(x['pe'])}</td><td>{cell(x['roe'])}</td><td>{x['news']}</td>"
                f"<td style='color:{color.get(x['verdict'],'#000')};font-weight:700'>{x['verdict']}</td></tr>\n")
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>NSE Smart Money Radar</title><style>
:root{{color-scheme:light}} body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;
background:#fff;color:#1a1a1a;max-width:980px;margin:24px auto;padding:0 16px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:#57606a;margin-bottom:16px}}
.pill{{display:inline-block;padding:4px 10px;border-radius:14px;font-weight:700;color:#fff;
background:{'#1a7f37' if stance=='RISK-ON' else ('#cf222e' if stance=='RISK-OFF' else '#9a6700')}}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{padding:7px 9px;
border-bottom:1px solid #eaecef;text-align:right}} th:first-child,td:first-child{{text-align:left}}
th{{background:#f6f8fa;text-align:right}} .note{{color:#57606a;font-size:12px;margin-top:14px;
line-height:1.5}}</style></head><body>
<h1>NSE Smart Money Radar</h1>
<div class="sub">As of <b>{asof.date()}</b> &nbsp;·&nbsp; Universe: {uni} &nbsp;·&nbsp; top {top} momentum</div>
<p>Market stance: <span class="pill">{stance}</span> &nbsp; regime mult {reg:.2f},
12m proxy return {mkt12:+.1%}</p>
<table><thead><tr><th>Symbol</th><th>Mom</th><th>Flow</th><th>VolX</th><th>Dlv%</th>
<th>Deal</th><th>P/E</th><th>ROE%</th><th>News</th><th>Verdict</th></tr></thead>
<tbody>{trs}</tbody></table>
<p class="note"><b>How to read:</b> Mom = momentum strength · Flow = money-flow (accumulation&gt;0) ·
VolX = volume vs median · Dlv% = delivery conviction · Deal = recent bulk/block · P/E,ROE,News = live.
<b>VERDICT is confluence-based</b> (momentum + delivery + flow + value + clean news), never one column.<br>
<b>Decision-support only — NOT auto-trading, NOT validated alpha, NOT financial advice.</b>
Edge is modest (~0.4–0.7 Sharpe) and survivorship-uncertain; verify before acting and start small.</p>
</body></html>"""
    out = Path("Reports") / "radar.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)


if __name__ == "__main__":
    main()
