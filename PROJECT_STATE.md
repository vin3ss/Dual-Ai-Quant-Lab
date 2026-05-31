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
| backtest | `backtest/validation.py` | ✅ implemented | walk-forward, holdout, regime stress, param sensitivity; see issues #12, #13 |
| data | `data/market_data.py` | ✅ synthetic | `make_synthetic_data` for offline demo/tests |
| data | `data/loaders.py` | 🟡 real bhavcopy CSV works; live adapters lazy | `load_universe()`; now maps real NSE bhavcopy columns (legacy TIMESTAMP/CLOSE/TOTTRDQTY + UDiFF TckrSymb/ClsPric/TtlTradgVol); full pipeline validated end-to-end on bhavcopy-shaped CSV; point-in-time + survivorship guards; nsepython/nsefin adapters still `NotImplementedError`. See `Research/Datasets/REAL_DATA_RUNBOOK.md` |

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
10. ~~**[MED→HIGH] Macro tilt is annihilated by sector-neutralization.**~~ ✅ FIXED
   (2026-05-31). Added `PortfolioConstructor.apply_sector_tilt()`: applies the macro view
   as a sector-budget overlay AFTER name selection (scales each name by
   `1 + strength*tilt`, renormalizes to preserve gross), so it survives instead of being
   demeaned. Tests in `tests/test_macro_integration.py` incl. one proving the old blending
   path zeroes out while the overlay path works. Usage: blend momentum/quality/etc. as
   before, but route macro through `apply_sector_tilt`, not `combine`. Refined 2026-05-31
   (Gemini audit #4): now SIGN-AWARE — `weight + |weight|*strength*tilt`, so a bullish tilt
   increases longs and REDUCES shorts (the old multiplicative form deepened shorts). Short
   case covered by a test.

## Open issues — Gemini red-team audit (2026-05-31)

14. **[MED→HIGH] Execution-price simultaneity.** Backtest earns close(t-1)→close(t) on
   weights decided at close(t-1) — i.e. signal and execution at the same close, which isn't
   tradable (NSE close is a 3:00–3:30 VWAP). Should execute at next open/VWAP. Bias real but
   smaller on monthly bars; Gemini's "3-5% CAGR" is an estimate, unverified. Add an
   execution-lag / next-open option to the engine.
15. **[HIGH] Vol-target ↔ capacity decoupling.** RiskManager sizes for a vol target, then the
   backtest clips trades to ADV capacity and the overflow silently becomes cash → realized
   exposure/vol decouples from target. Fix: make capacity-aware sizing (redistribute clipped
   capital to next names) or at least recompute/report realized exposure after clipping.
16. **[HIGH] Bhavcopy "Top-N" survivorship.** Deriving the universe from daily bhavcopy by
   turnover/mcap is itself a look-ahead filter (drops crashing names pre-crash). Reinforces
   the step-7 requirement: source a true point-in-time index-constituent list; don't derive
   the universe from bhavcopy alone.
17. **[MED] Uninvested cash earns 0%.** When regime de-risks to cash, the backtest accrues 0
   on the uninvested fraction, unfairly penalizing the regime detector. Accrue ~RBI
   risk-free (repo, ~6%) on `1 - invested`. This makes results MORE honest (and slightly
   better), so fix before judging regime parameters.

## Open issues — Sentiment signal

11. **[MED] Sentiment panel leaks via timestamp errors / stale fills (ChatGPT).**
   `data.news` must be indexed by publication/availability timestamp, not fiscal period,
   call date, or article/event date. Forward-filled stale sentiment overstates persistence;
   coverage is survivorship-biased if delisted/less-covered names are absent; NLP scores may
   be vendor/model-revised after the fact. (Minor: panel columns are upper-cased — relies on
   the loader's upper-cased tickers to align; mixed-case universes would mismatch.)

## Open issues — Validation harness

12. **[HIGH] Validation can still overstate robustness (ChatGPT).** Walk-forward windows may
   overlap; repeated grid searches introduce multiple-testing bias; stress windows can be
   cherry-picked; OOS gets contaminated if reused for design decisions. Keep a final
   untouched holdout and log every parameter search.
13. ~~**[HIGH] Walk-forward windows have no lookback buffer.**~~ ✅ FIXED (2026-05-31).
   `_slice_data(..., lookback=N)` prepends N bars of history; `_run_scored_window` computes
   signals on the buffered data but scores returns/turnover/stats ONLY on the true window.
   Test proves a momentum fn has a real position on the first scored bar and buffer bars are
   excluded from OOS returns. Minor follow-up: train-window param selection (`_select_params`)
   still scores over the buffered train slice, not the exact train window — low impact (no
   future leak, just a marginally wider selection window).

## First real-data validation (2026-05-31) — VERDICT: no trustworthy edge yet

Ran momentum+regime on 3204 NSE stocks, 2019-2026 (month-end bhavcopy). Headline:
**IS Sharpe 1.48 → OOS Sharpe 0.04 (degradation 1.45).** Walk-forward OOS Sharpe 0.77
but fragile; regime thirds show momentum worked 2019-2023, died 2024-2026. The IS→OOS
collapse says the in-sample strength does not persist — treat as noise/artifact until the
data issues below are fixed. (Fixed `returns()` to `pct_change(fill_method=None)` so a
sparse universe no longer fabricates returns across gaps.)

## Open issues — surfaced by first real-data run

18. **[HIGH] Prices are corporate-action UNadjusted.** Raw bhavcopy close; splits/bonuses
   (e.g. HDFCBANK 2080→745) create fake ~±50% returns that momentum chases. Must use
   adjusted close (vendor) or apply a point-in-time corporate-actions file before any
   result is trustworthy. Biggest single contaminant right now.
19. **[HIGH] No liquidity filter / 3204-name universe.** Union of all EQ names ever listed;
   ~44% NaN, thousands of illiquid microcaps dominate the cross-section with untradeable
   noise, and the NaN-union is survivorship-flavoured. Restrict to a point-in-time liquid
   set (e.g. top-N by trailing ADV/turnover each month) — overlaps issue #16.

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
5b. ~~**Fix issue #10**~~ ✅ DONE — `apply_sector_tilt` sector-budget overlay.
6. ~~**Validation harness**~~ ✅ DONE — walk-forward, holdout, regime stress, param
   sensitivity (issues #12, #13 to harden). Engine core build-out complete.
7. **Real data CONNECTED** ✅ — 89 month-end bhavcopies (2019-2026) load via `data_in/`,
   EQ-series filtered, dedup-guarded, both legacy+UDiFF formats. First validation run done.
8. **REFINE against real data** ← NEXT, in priority order:
   (a) **#18 adjusted prices** — biggest contaminant; get adjusted close or a CA file.
   (b) **#19 liquidity filter** — restrict to point-in-time top-N by ADV; kill microcap noise.
   (c) engine fixes #17 (cash yield), #15 (vol/capacity), #14 (execution price).
   Re-run validation after each; only then judge whether momentum has a real edge.
9. **Paper→live** via Paytm Money `pyPMClient` behind a human-confirm switch — ONLY after a
   surviving OOS edge on adjusted, liquid data.
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
