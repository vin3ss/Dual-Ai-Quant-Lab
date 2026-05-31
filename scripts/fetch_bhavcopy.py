"""Download NSE UDiFF bhavcopy CSVs into data_in/bhavcopy/.

RUN THIS ON YOUR OWN MACHINE — NSE blocks datacenter/sandbox IPs, but a normal
home/office connection with a browser-like session works for personal use.

    # month-end files only (fast; ~12/yr) — enough for the monthly-bar engine:
    python -m scripts.fetch_bhavcopy --start 2019-01-01 --end 2024-12-31

    # every trading day (slower, needed for real ADV/capacity):
    python -m scripts.fetch_bhavcopy --start 2024-01-01 --end 2024-12-31 --daily

Stdlib only. Politely warms up an nseindia.com session for cookies, then pulls the
UDiFF zip per date and extracts the CSV. Skips dates already present and silently
skips holidays/weekends (404s). Not part of the tested engine core — it's a
convenience fetcher; verify a couple of files open before trusting a full run.
"""

from __future__ import annotations

import argparse
import calendar
import http.cookiejar
import io
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# UDiFF format (current; only exists from ~2024-07-08 onward)
UDIFF = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
# Legacy historical archive (older dates; may or may not still be served)
LEGACY = ("https://nsearchives.nseindia.com/content/historical/EQUITIES/"
          "{yyyy}/{mmm}/cm{dd}{mmm}{yyyy}bhav.csv.zip")


def urls_for(d: date) -> list[str]:
    ymd = d.strftime("%Y%m%d")
    mmm = d.strftime("%b").upper()
    return [
        UDIFF.format(ymd=ymd),
        LEGACY.format(yyyy=d.year, mmm=mmm, dd=d.strftime("%d")),
    ]


def make_opener() -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", UA),
        ("Accept", "*/*"),
        ("Referer", "https://www.nseindia.com/all-reports"),
    ]
    try:  # warm up to collect anti-bot cookies
        op.open("https://www.nseindia.com", timeout=15).read(64)
    except Exception:
        pass
    return op


def month_end_targets(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        last = date(y, m, calendar.monthrange(y, m)[1])
        if start <= last <= end:
            out.append(last)
        m, y = (1, y + 1) if m == 12 else (m + 1, y)
    return out


def daily_targets(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:  # skip weekends; holidays handled by 404 skip
            out.append(d)
        d += timedelta(days=1)
    return out


def fetch_one(op, target: date, outdir: Path, lookback: int = 6) -> str | None:
    """Try target date, stepping back up to `lookback` days to land on a trading day."""
    for i in range(lookback):
        d = target - timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        dest = outdir / f"BhavCopy_{ymd}.csv"
        if dest.exists():
            return ymd
        for url in urls_for(d):
            try:
                raw = op.open(url, timeout=30).read()
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
                    dest.write_bytes(z.read(csv_name))
                return ymd
            except Exception:
                continue
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--daily", action="store_true", help="every trading day (default: month-end only)")
    ap.add_argument("--out", default="data_in/bhavcopy")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    targets = daily_targets(start, end) if args.daily else month_end_targets(start, end)
    print(f"Fetching {len(targets)} {'daily' if args.daily else 'month-end'} bhavcopies -> {outdir}")

    op = make_opener()
    ok = miss = 0
    for t in targets:
        got = fetch_one(op, t, outdir)
        if got:
            ok += 1
            print(f"  ok  {t} -> {got}")
        else:
            miss += 1
            print(f"  --  {t} (no file found; holiday or blocked)")
        time.sleep(0.4)  # be polite

    print(f"\nDone: {ok} downloaded/present, {miss} missing. Now run:")
    print("  python -m scripts.run_real_validation")


if __name__ == "__main__":
    main()
