# Real-Data Runbook — feeding NSE Alpha Forge actual market data

The engine reads real data through `load_universe()`. The validated on-ramp is the
**official NSE bhavcopy CSV** path. (Live `nsepython`/`nsefin` API adapters are
intentionally still stubs — run those on your own machine once their schema is
validated; do not ship untested scrapers, and NSE blocks automated access without a
proper session.)

## 1. Get the data (publicly available, free)

- **Bhavcopy (EOD OHLCV + volume):** download NSE's daily "Securities bhavcopy"
  CSVs (legacy `cmDDMMMYYYYbhav.csv` or the newer UDiFF/`sec_bhavdata_full` files)
  and drop them all in one folder. The loader auto-detects the common column names:
  - date: `TIMESTAMP`, `TradDt`, `DATE1`
  - symbol: `SYMBOL`, `TckrSymb`
  - close: `CLOSE`, `CLOSE_PRICE`, `ClsPric`
  - volume: `TOTTRDQTY`, `TTL_TRD_QNTY`, `TtlTradgVol`
- **Sectors** (optional but recommended): a CSV with `symbol,sector` columns.
- **Fundamentals** (for QualitySignal): a CSV with `symbol,availability_date,roe,accruals,earnings_vol`.
  **Must** use `availability_date` (filing date), never period-end — the loader rejects
  period-end-only data to block the most common Indian-backtest leak.
- **Macro** (for MacroSignal): a CSV with `date,repo_rate,cpi,iip` indexed by release date.
- **Point-in-time constituents (issue #16):** a historical index-membership list
  (e.g. Nifty 500 changes over time). **Do not** derive the universe by filtering
  bhavcopy "top N by turnover" — that silently drops crashing names before the crash
  (survivorship). Join bhavcopy strictly to the PiT constituent set instead.

## 2. Point the loader at it

```python
from nse_alpha_forge.data import load_universe, LoaderConfig

cfg = LoaderConfig(
    source="csv",
    bhavcopy_dir="/path/to/bhavcopy_csvs",
    sectors_path="/path/to/sectors.csv",            # optional
    fundamentals_path="/path/to/fundamentals.csv",  # optional
    macro_path="/path/to/macro.csv",                # optional
    resample="ME",                                  # monthly bars
)
data = load_universe("2015-01-01", "2025-12-31", config=cfg)
```

Then run signals → portfolio → risk → backtest, or the validation harness
(`walk_forward`, `holdout_split`, `regime_stress`) — now with a `lookback` buffer so
momentum/regime have history at each window start.

## 3. Heed the warnings

The loader emits loud `DataQualityWarning`s for survivorship, raw-vs-adjusted close,
missing corporate actions, and missing sectors. Those are not noise — read them. Open
issues #6–#17 in `PROJECT_STATE.md` list the biases that remain even with real data
(execution-price, capacity/vol decoupling, cash yield, etc.); fix those before trusting
any backtest number.

## 4. Live API (later, on your machine)

`source="nsepython"` / `"nsefin"` adapters are stubs that raise `NotImplementedError`
with guidance. Wire them on your own machine where the library handles the NSE session
legitimately, validate the returned schema against the column expectations above, then
add a fixture test before relying on them.
