"""Fetch free NSE 'big fish' data into data_in/smartmoney/ (RUN LOCALLY — NSE blocks
datacenter IPs). Best-effort, stdlib-only, with a browser-like session warmup.

Pulls:
  - DELIVERY %  : sec_bhavdata_full_DDMMYYYY.csv  -> delivery.csv  (date,symbol,deliv_pct)
  - BULK deals  : current bulk.csv                -> bulk_deals.csv (date,symbol,action,quantity)
  - BLOCK deals : current block.csv               -> block_deals.csv
  - FII/DII     : fiidiiTradeReact API (market-aggregate) -> fii_dii.csv (date,fii_net,dii_net)

These feed nse_alpha_forge.analytics.smart_money (deal_pressure, delivery_accumulation) and
the live enrich_holdings screen — NOT the backtest (not validated alpha, not point-in-time
fundamentals). Coverage caveat: NSE's per-date historical bulk/block/delivery archives use
shifting URL patterns and an authenticated API; this fetcher grabs delivery by month-end and
the current bulk/block snapshot. Deep history needs the NSE historical API or a vendor.

    python -m scripts.fetch_smart_money --start 2024-07-01 --end 2026-05-31
"""

from __future__ import annotations

import argparse
import calendar
import csv
import http.cookiejar
import io
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DELIVERY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
BULK_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"
FIIDII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"


def opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Accept", "*/*"),
                     ("Referer", "https://www.nseindia.com/")]
    try:
        op.open("https://www.nseindia.com", timeout=15).read(64)
    except Exception:
        pass
    return op


def month_ends(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        d = date(y, m, calendar.monthrange(y, m)[1])
        if start <= d <= end:
            out.append(d)
        m, y = (1, y + 1) if m == 12 else (m + 1, y)
    return out


def _get(op, url):
    return op.open(url, timeout=30).read()


def fetch_delivery(op, start, end, outdir: Path):
    rows = []
    for me in month_ends(start, end):
        for i in range(6):  # step back to a trading day
            d = me.fromordinal(me.toordinal() - i)
            try:
                raw = _get(op, DELIVERY_URL.format(ddmmyyyy=d.strftime("%d%m%Y")))
                rdr = csv.DictReader(io.StringIO(raw.decode("utf-8", "ignore")))
                rdr.fieldnames = [c.strip().upper() for c in (rdr.fieldnames or [])]
                for r in rdr:
                    r = {k.strip().upper(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                    if r.get("SERIES") != "EQ":
                        continue
                    rows.append({"date": me.isoformat(), "symbol": r.get("SYMBOL"),
                                 "deliv_pct": r.get("DELIV_PER")})
                print(f"  delivery ok {me}"); break
            except Exception:
                continue
        time.sleep(0.4)
    if rows:
        _write(outdir / "delivery.csv", ["date", "symbol", "deliv_pct"], rows)


def fetch_deals(op, url, outdir, fname):
    try:
        raw = _get(op, url).decode("utf-8", "ignore")
        rdr = list(csv.DictReader(io.StringIO(raw)))
        rows = []
        for r in rdr:
            r = {k.strip().lower(): v for k, v in r.items()}
            sym = r.get("symbol") or r.get("security name")
            act = (r.get("buy/sell") or r.get("buy / sell") or "").strip().upper()
            qty = (r.get("quantity traded") or r.get("quantity") or "0").replace(",", "")
            dt = r.get("date") or r.get("deal date")
            if sym and act:
                rows.append({"date": dt, "symbol": sym, "action": act, "quantity": qty})
        if rows:
            _write(outdir / fname, ["date", "symbol", "action", "quantity"], rows)
            print(f"  {fname}: {len(rows)} deals")
    except Exception as e:
        print(f"  {fname} skipped: {type(e).__name__}")


def fetch_fiidii(op, outdir):
    try:
        data = json.loads(_get(op, FIIDII_URL).decode("utf-8", "ignore"))
        rows = []
        for r in data:
            rows.append({"date": r.get("date"), "category": r.get("category"),
                         "net": r.get("netValue")})
        if rows:
            _write(outdir / "fii_dii.csv", ["date", "category", "net"], rows)
            print(f"  fii_dii: {len(rows)} rows")
    except Exception as e:
        print(f"  fii_dii skipped: {type(e).__name__}")


def _write(path: Path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data_in/smartmoney")
    args = ap.parse_args()
    outdir = Path(args.out)
    op = opener()
    print(f"Fetching NSE big-fish data -> {outdir} (run locally; needs NSE access)")
    fetch_delivery(op, date.fromisoformat(args.start), date.fromisoformat(args.end), outdir)
    fetch_deals(op, BULK_URL, outdir, "bulk_deals.csv")
    fetch_deals(op, BLOCK_URL, outdir, "block_deals.csv")
    fetch_fiidii(op, outdir)
    print("Done. These feed enrich_holdings' smart-money overlay (monitor only, not backtest).")


if __name__ == "__main__":
    main()
