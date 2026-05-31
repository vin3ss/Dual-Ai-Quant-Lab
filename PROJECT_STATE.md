# PROJECT STATE — single source of truth

> Both AI agents (Claude = research/critic, ChatGPT = architect/builder) read this
> file at the start of every working session so we stay in sync. Update it whenever
> a module's status changes. Last updated: 2026-05-31.

## Vision

**NSE Alpha Forge** — a systematic trading engine for Indian equities (NSE/BSE).
Data flows one direction through four stages, with a backtester wrapped around the
whole chain:

```
data → alpha signals → portfolio construction → risk → execution
                         ↑ backtest validates the whole chain ↑
```

## How we work (dual-AI loop)

- **Claude** — research + adversarial critic (look-ahead, survivorship, overfitting, capacity).
- **ChatGPT** — architect + builder. Has **pull-only** GitHub access, so it delivers
  **patch-ready code**, not direct commits.
- **Integration** — Claude applies ChatGPT's patches to the real files, runs tests +
  demo, commits locally. The human (Vineeth) runs `git push`.

Golden rule: **be suspicious of good backtest results.** A great-looking backtest
almost always hides a leak. The critic's job is to find it before capital does.

## Module status

| Stage | Module | Status | Notes |
|---|---|---|---|
| alpha | `technical/momentum.py` | ✅ implemented | 12-1 risk-adjusted momentum |
| alpha | `fundamental/quality.py` | ✅ implemented | ROE + accruals + earnings stability |
| alpha | `regime/__init__.py` | ✅ implemented + refined | per-date multiplier [0,1]; macro overlay refinement pending (issue #6) |
| alpha | `sentiment/` | ✅ implemented | consumes date×ticker news panel; z-scored, lagged; neutral when absent; issue #11 |
| alpha | `macro/` | ✅ implemented (sector tilt) | repo/CPI/IIP → sector tilt; neutral when absent; see issues #9, #10 |
| alpha | `options/` | ✅ implemented (overlay) | PCR/FII-deriv → bounded [-1,1] conviction; neutral when absent |
| portfolio | `portfolio/constructor.py` | ✅ implemented | signal blend → top-quantile weights |
| risk | `risk/manager.py` | ✅ implemented | caps + vol target + DD de-risk + `apply_regime` hook |
| execution | `execution/__init__.py` | 🔴 stub | target broker: Paytm Money Open API (`pyPMClient`) |
| backtest | `backtest/engine.py` | ✅ implemented | vectorized, shift(1) anti-leakage; now itemized costs + impact + capacity cap |
| backtest | `backtest/costs.py` | ✅ implemented | per-side STT/exchange/SEBI/GST/stamp; ADV-participation impact; capacity clipping |
| data | `data/market_data.py` | ✅ synthetic | `make_synthetic_data` for offline demo/tests |
| data | `data/loaders.py` | 🟡 CSV/bhavcopy works; live adapters lazy | `load_universe()`; point-in-time + survivorship guards; nsepython/nsefin adapters are `NotImplementedError` pending schema validation |

Legend: ✅ done · 🟠 partial / not integrated · 🔴 stub

## Open issues — RegimeDetector

1. ~~**[MED] Frequency mismatch.**~~ ✅ DONE — macro windows derive from `bars_per_year`.
2. ~~**[MED] Survivorship in fallback index.**~~ ✅ DONE — equal-weight fallback now emits a
   `RuntimeWarning`; index built from returns.
3. ~~**[LOW→MED] Hand-tuned magic numbers.**~~ ✅ DONE — all thresholds moved to the constructor.
6. **[MED] VIX rolling-rank saturates on sustained stress (NEW, 2026-05-31).** The macro
   VIX gate uses `rolling(bars_per_year).rank(pct=True)`. When VIX jumps and *stays* high,
   the rolling window fills with high values and the percentile rank collapses back toward
   ~0.5 — so a sustained high-vol regime stops triggering the gate after ~`bars_per_year`
   bars. Verified: injecting a VIX spike that holds barely moved the multiplier. Fix
   options: compare VIX to a *longer* trailing baseline (e.g. 3y) than the ranking window,
   or use a level/z-score vs long-run mean instead of a short rolling rank. Defer until
   real macro data is connected (step 3) so we calibrate against actual India VIX history.
4. ~~**[LOW] Not wired into pipeline.**~~ ✅ DONE (2026-05-31). `RiskManager.apply_regime`
   added + wired into demo. Tests: crash-drawdown reduction (51.8%→28.3% on the test
   scenario) and all-dates no-future-leakage. Demo Sharpe 0.29→0.46, maxDD 14.1%→10.5%.
   Note: ChatGPT's proposed shift-invariance test was buggy (compared mismatched slices);
   replaced with a proper detector leakage test perturbing all future bars.
5. **[LOW] `prices.iloc[0]` base.** NaN at t0 drops a ticker for all history → survivorship
   vector. Fix: normalize by first valid value per column, or build index from returns.

## Open issues — Cost / capacity model

7. **[MED] Coarse capacity on monthly bars + unmodeled frictions (NEW, 2026-05-31).**
   With monthly resampling, "ADV" is the mean of ~20 *monthly* dollar-volume bars, not a
   true daily ADV, so participation/capacity are approximate; they become realistic only
   on daily data. Also still NOT modeled (per ChatGPT, kept as explicit caveats in
   `costs.py`): bid-ask spread, open/close auction liquidity, order-book depth, liquidity
   droughts in crashes, partial fills (approximated as clipping), and tax on realised
   gains. Treat backtest costs as a *floor*, not the truth. Revisit when daily data lands.

## Open issues — Options-flow signal

8. **[MED] Raw-data contract is simplified (logged 2026-05-31, ChatGPT review).** The
   module expects a clean date×ticker PCR/FII panel. Real NSE option-chain data is richer
   and messier (expiry, strike, CE/PE OI, OI change, volume, IV, timestamps) and needs an
   upstream aggregator by expiry/strike before this overlay is production-realistic.
   Market-wide FII *derivative* data is intentionally rejected here and should feed
   regime/macro, not cross-sectional alpha. Also: "low PCR = bullish" is a hypothesis, not
   proven alpha — validate by regime and expiry bucket. Data-bias risks: stale EOD
   snapshots, expiry rolls, vendor-cleaned OI, illiquid single-stock options.

## Open issues — Macro signal

9. **[MED] Macro data can leak via revisions / reference-period confusion (ChatGPT).**
   `data.macro` must be indexed by release/availability date, not reference month. CPI/IIP
   revisions, RBI event timing, and month-end resampling can all create look-ahead unless
   handled by a proper release calendar.
10. **[MED→HIGH] Macro tilt is annihilated by sector-neutralization (Claude, verified).**
   Macro emits a *uniform per-sector* tilt, but `PortfolioConstructor.to_weights` with the
   default `sector_neutral=True` demeans within each sector — which zeroes the macro
   contribution entirely (probe confirmed: collapses to 0). Fix: apply macro as a
   *sector-allocation overlay* in the portfolio/risk layer (tilt sector budgets), NOT as a
   cross-sectional name score that gets sector-demeaned; or explicitly exempt macro from
   neutralization. Until fixed, do not rely on macro in a sector-neutral configuration.

## Open issues — Sentiment signal

11. **[MED] Sentiment panel leaks via timestamp errors / stale fills (ChatGPT).**
   `data.news` must be indexed by publication/availability timestamp, not fiscal period,
   call date, or article/event date. Forward-filled stale sentiment overstates persistence;
   coverage is survivorship-biased if delisted/less-covered names are absent; NLP scores may
   be vendor/model-revised after the fact. (Minor: panel columns are upper-cased — relies on
   the loader's upper-cased tickers to align; mixed-case universes would mismatch.)

## Roadmap (priority order)

1. ~~**Wire regime into RiskManager**~~ ✅ DONE (2026-05-31).
2. ~~**Refine RegimeDetector** per open issues 1–3, 5.~~ ✅ DONE (2026-05-31). New issue #6 logged.
3. **Connect real data** — 🟡 loader framework DONE (`load_universe`, CSV/bhavcopy path,
   point-in-time + survivorship guards, parquet cache). Remaining: wire the live
   `nsepython`/`nsefin` adapters (currently lazy stubs) once their schema is validated,
   and source a real point-in-time constituent + fundamentals dataset.
4. ~~**Honest cost & capacity**~~ ✅ DONE (2026-05-31). Itemized per-side cost model
   (STT/exchange/SEBI/GST/stamp), nonlinear ADV-participation impact, capacity cap that
   clips oversized trades; `volume` added to MarketData + loader. New issue #7 logged.
5. ~~**Fill remaining signals**~~ ✅ DONE — options (overlay), macro (sector tilt), sentiment
   all implemented + tested. Core signal set complete.
5b. **Fix issue #10** — wire macro as a sector-budget overlay (it's inert under
   sector-neutralization today). ← NEXT (quick, high-value)
6. **Validation harness** — walk-forward, out-of-sample holdout, regime stress tests.
7. **Paper → live execution** via Paytm Money `pyPMClient`, behind a human-confirm switch.

## Conventions (non-negotiable)

- Every signal is **point-in-time**: at date t, use only data available before t (`shift`).
- Fundamentals lagged to **filing/availability date**, never period-end.
- Model **real Indian costs**: brokerage, STT, exchange, GST, stamp duty, **impact**.
- No live order placement without an explicit human-confirmed flag.
- Prefer small, testable increments; add a unit test with every module.

## Broker / execution target

Paytm Money **Open API** (REST) + official Python SDK `pyPMClient`: orders (regular/
cover/bracket), positions, portfolio, funds, live market data; NSE/BSE equities + F&O.
Requires a KYC-ready Paytm Money equity account + a developer app (API key/secret).
Docs: https://developer.paytmmoney.com/ · SDK: https://github.com/paytmmoney/pyPMClient
