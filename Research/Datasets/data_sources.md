# Indian Market Data Source Catalog

*For NSE Alpha Forge. Free sources are great for research; for production you will want a licensed feed. Always check the terms of use — several "free" NSE wrappers scrape endpoints that NSE can change or rate-limit at any time.*

## Free / open

| Source | What you get | Access |
|---|---|---|
| **NSE bhavcopy** | EOD OHLCV for equities & F&O, delivery %, security-wise data | CSV download from NSE; or via wrappers below |
| **NSE FII/DII activity** | Daily provisional & combined cash/derivative flows — key regime input | NSE site / `nsefin` |
| **NSE option chain** | Full chain with OI, volume, optional Greeks | `nsefin`, `nsepython` |
| **`nsepython`** (PyPI) | Quotes, indices, F&O, historical prices | `pip install nsepython` |
| **`nsefin`** (PyPI) | Bhavcopy (equity + F&O), option chain w/ Greeks, FII/DII as pandas | `pip install nsefin` |
| **bhavCopy-downloader** (GitHub) | Batch NSE/BSE bhavcopy + derivatives by date/index | clone from GitHub |
| **screener.in** | Fundamentals, ratios, financials (manual / scrape per their terms) | web |
| **RBI** | Macro: rates, CPI, IIP, money supply | RBI site / DBIE |
| **Google Trends** | Search-interest alt-data | `pytrends` |

## Broker / vendor APIs

| Source | Notes |
|---|---|
| **Zerodha Kite Connect** | Most popular retail algo API; paid; historical + live + order placement |
| **ICICI Breeze** | Free for ICICIdirect customers; full option chain (OHLC, OI, volume), historical |
| **Upstox / Angel One SmartAPI / Fyers** | Comparable broker APIs |
| **TrueData** | Authorized L1 vendor, NSE/BSE/MCX, WebSocket real-time + historical (paid) |
| **Global Datafeeds (GDFL)** | Authorized real-time/historical/option-chain APIs (paid) |

## Recommended split

- **Research / backtest:** bhavcopy + `nsefin`/`nsepython` for EOD, FII/DII, option chain. Free, good enough to prove an edge.
- **Point-in-time fundamentals:** this is the hard part for free sources — budget for a licensed point-in-time fundamentals dataset before trusting any fundamental-factor backtest (avoids survivorship + restatement bias).
- **Production execution:** a broker API (Kite/Breeze/Fyers) for live data + order placement.

## Sources

- [Data Sources for Algo Trading in India — Free & Paid (Endovia Wealth)](https://www.endoviawealth.com/data-sources-for-algo-trading-in-india-free-paid-options/)
- [nsefin (PyPI)](https://pypi.org/project/nsefin/)
- [nsepython (PyPI)](https://pypi.org/project/nsepython/)
- [ICICI Breeze Trading API](https://www.icicidirect.com/futures-and-options/api/breeze)
- [bhavCopy-downloader (GitHub)](https://github.com/girishg4t/bhavCopy-downloader)
- [stock-nse-india API (GitHub)](https://github.com/hi-imcodeman/stock-nse-india)
