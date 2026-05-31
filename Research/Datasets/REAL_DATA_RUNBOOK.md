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

## 3b. Point-in-time index constituents (issue #21 — the rigid universe)

Drop a `data_in/constituents.csv` and the validation switches from the liquidity filter
to true index membership automatically. Two accepted formats:

- **Snapshot:** `date,symbol` — the member list as of each reconstitution date. The engine
  uses the most recent snapshot ≤ each backtest date.
- **Interval:** `symbol,start_date,end_date` — membership windows (blank `end_date` = still in).

**Tooling:** `scripts/build_constituents.py` assembles a best-effort `constituents.csv` by
walking BACKWARD from the current NSE constituent list through reconstitution events you
curate in `data_in/index_events.csv` (`effective_date,add_symbol,remove_symbol,source`).
Symbol renames/mergers go in `data_in/symbol_aliases.csv` (`old_symbol,new_symbol`). Run:
```bash
python -m scripts.build_constituents --index NIFTY500 --min-date 2019-01-01
```
The irreducible manual step is curating `index_events.csv` from NSE/NiftyIndices semi-annual
reconstitution circulars (Jan/Jul cut-offs). Without events it emits only the current
(survivorship-biased) baseline.

**Sourcing reality (researched 2026-05-31):** there is NO clean, free, point-in-time
Nifty-500 membership dataset. Free sources give only *current* constituents + price history.
True reconstitution history must be either (a) assembled by hand from NSE/niftyindices
semi-annual reconstitution circulars, or (b) bought (niftyindices historical / CMIE Prowess).
Until you have this file, the backtest uses the liquidity-defined universe, which carries the
selection bias documented in issue #21 — treat those results as indicative, not final.

## 4. Live API (later, on your machine)

`source="nsepython"` / `"nsefin"` adapters are stubs that raise `NotImplementedError`
with guidance. Wire them on your own machine where the library handles the NSE session
legitimately, validate the returned schema against the column expectations above, then
add a fixture test before relying on them.
