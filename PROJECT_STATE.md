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

14. **[HIGH — both AIs' #1 priority] Execution-price simultaneity / look-ahead.** Backtest earns close(t-1)→close(t) on
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

**Update — after liquidity filter (#19):** restricting to liquid top-300 made momentum
WORSE (IS 1.17 → OOS -0.09, WF Sharpe 0.38), confirming the earlier positive was microcap
noise.

**DEFINITIVE run (2026-05-31): full CA adjustment (439 actions/215 symbols) + survivorship-free
bhavcopy + liquid universe → WF OOS Sharpe ~0.83** (CAGR 4.8%, MaxDD 7.6%; regime thirds
1.38/1.33/-0.05; holdout IS 1.26→OOS 0.37). Honest verdict: **NSE 12-1 momentum is a real,
moderate factor (~0.8 WF Sharpe), strong 2019-2023, in drawdown since 2024.** Treat as an
optimistic ceiling — engine realism issues #14/#15/#17 still unmodeled (will pull toward
~0.5-0.7); universe is liquidity-defined PiT, not true index membership. Arc:
raw 0.77(noise) → liquid-unadj 0.38 → Yahoo survivor-only 1.06(hallucination) →
survivorship-free+adjusted **0.83**.

**Earlier — partial-adjust run: survivorship-free bhavcopy + corporate-action adjusted (2026-05-31).**
`scripts/fetch_corporate_actions.py` pulls split/bonus factors (Yahoo split history) into the
loader's `corporate_actions_path`; applied to the bhavcopy this fixes fake split returns
WITHOUT dropping dead names (verified: HDFCBANK Aug-25 -52.8% → -5.7%). Run on liquid top-300,
CA covering the ~76 most-liquid split names: **WF OOS Sharpe ~0.66** (CAGR 3.7%, MaxDD 7.8%),
regime thirds 1.41 / 1.24 / -0.10. This sits between raw-bhavcopy 0.38 and the survivor-only
Yahoo 1.06 — exactly as expected: adjustment lifts it off 0.38, survivorship-free keeps it far
below the 1.06 hallucination. **Best honest estimate of NSE 12-1 momentum so far: ~0.6 WF
Sharpe, real but modest, currently in drawdown.** (Partial CA coverage — re-run with
`fetch_corporate_actions --top-n 500` for the definitive number.)

**Update — ADJUSTED data (Yahoo, top-150 liquid, #18 addressed via yfinance):** WF OOS
Sharpe rose to **1.06** (CAGR 5.2%, vol 5%, maxDD 4.8%); regime thirds Sharpe ~1.35 in
2019-2023 then ~0.13 in 2024-2026. Single 70/30 holdout still collapses (IS 1.59→OOS 0.07)
because the OOS slice IS the 2024-26 momentum drawdown. Read: adjusting prices + liquid
universe lifts walk-forward momentum to a *suggestive* ~1.0, BUT this 150-name set is the
CURRENT liquid universe with Yahoo dropping delisted/renamed names → **survivorship-biased,
so 1.06 is optimistic.** Not a green light. Momentum looks real-ish 2019-2023, regime-broken
since. Main remaining caveat: survivorship / point-in-time constituents (#16). Also: regime
gate did NOT rescue the 2024-26 period — investigate whether it actually de-risked.

## Decision (2026-05-31, after ChatGPT + Gemini consult)

Both AIs agree: **fix engine realism #14/#15/#17 FIRST** (order: #14 execution → #17 cash
yield → #15 vol/capacity). Gemini frames #14 as a look-ahead leak (signal at month-end close
executed at that same close), not mere realism — top priority. Contested #2: ChatGPT says add
quality next; Gemini ranks quality LAST (piling factors on a discretionary universe) and puts
true index constituents second. DEFERRED until after realism fixes. ChatGPT cheap win adopted:
a **momentum health dashboard** (rolling 12m OOS Sharpe, drawdown, sector exposure, cash%,
turnover/capacity clips, hit-rate by regime) to tell whether 2024-26 is normal cyclicality or
strategy decay. Sample-size caveat (Gemini): 7yr / ~5 walk-forward windows over the craziest
NSE bull run is statistically thin — do NOT deploy capital on it.

## Open issues — surfaced by first real-data run

21. **[HIGH] Universe construction is discretionary & result-sensitive (Gemini #3 + Claude
   test).** Gemini's hypothesis: ranking liquid universe by turnover (price×vol) pre-selects
   momentum winners (price up → turnover up → enters universe; crash → turnover down → exits
   before momentum holds it down) → inflates Sharpe. EMPIRICAL TEST on adjusted data: ranking
   by raw volume gave HIGHER WF Sharpe (0.94) than turnover (0.83) — so the *direction* of
   Gemini's mechanism did NOT hold, but it proved the result swings ~0.1 Sharpe on an arbitrary
   universe choice = fragility. Resolution: move to a **rigid external index constituent set**
   (Nifty 500 PiT membership) so universe selection isn't discretionary or price-contaminated.

20. **[HIGH] Regime gate is mis-timed / near-useless on real monthly data (Claude, verified
   2026-05-31).** Inspected the multiplier over the adjusted Yahoo sample: it stayed at 1.00
   (full risk) through the worst down months (Oct-24 -7.8%, Feb-25 -8.6%, Mar-26 -10.6%) and
   cut to 0.42 during *rising* months (Apr-Aug 2025) — it de-risks into rallies. With-gate vs
   no-gate is a wash (Sharpe 1.21 vs 1.17, MaxDD 8.07% vs 8.87%), so the tiny benefit is luck,
   not timing. Root cause: 6/12-month MAs + 36-month vol percentile + shift(1) = far too laggy
   on monthly bars (compounds with #6 VIX-rank saturation).
   **Redesigned (2026-05-31, ChatGPT):** leading gate = drawdown-from-peak + short/long vol
   ratio + VIX z-score vs long baseline. Now REACTS to drawdowns (cut to 0.35 after Oct-24
   crash). BUT verified it WHIPSAWS on monthly bars (Gemini's predicted failure): de-risked
   0.35 into the +7.8% Mar-25 bounce and 0.35 into the +12.4% Apr-26 recovery. Kept (it's
   mechanically sound) but its performance is NOT to be trusted/tuned on survivorship-biased
   data. Gate-validation protocol before trusting it (Gemini): (1) "dumb-beta" test — gate
   must improve buy-and-hold Nifty risk-adjusted return, not just this momentum book; (2)
   parameter-plateau — only deploy if Sharpe is robust across a threshold grid, not a spike;
   (3) out-of-sample geography — same logic should help a US/EU index. Use strictly EXPANDING
   (not full-sample) means for VIX baseline to avoid future leak.

18. **[HIGH] Prices are corporate-action UNadjusted.** Raw bhavcopy close; splits/bonuses
   (e.g. HDFCBANK 2080→745) create fake ~±50% returns that momentum chases. Must use
   adjusted close (vendor) or apply a point-in-time corporate-actions file before any
   result is trustworthy. Biggest single contaminant right now.
19. ~~**[HIGH] No liquidity filter.**~~ ✅ ADDRESSED (2026-05-31). `portfolio/universe.py`
   `apply_liquidity_filter` (point-in-time top-N by trailing turnover) + tests. Re-run on
   liquid top-300: momentum got WORSE (IS 1.17 → OOS -0.09; WF Sharpe 0.77→0.38) — i.e. the
   earlier mild positive was microcap noise. Tradable-universe momentum shows no OOS edge
   here. (NaN-union survivorship still partly remains; tighten with PiT constituents later.)

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
8. **REFINE against real data** — partial: ✅#19 liquidity filter, ✅#18 adjusted via Yahoo
   (but Yahoo reintroduced survivorship), ✅ regime gate redesigned (#20, whipsaws though).

9. **🔴 TOP PRIORITY (Gemini call, Claude concurs): build a SURVIVORSHIP-FREE + point-in-time
   universe BEFORE any more alpha/gate work.** Momentum on survivor-only data (Yahoo) is the
   deadliest bias combo — the ~1.06 Sharpe is a hallucination; honest baseline ~0.4. KEY
   INSIGHT: the **bhavcopy is already survivorship-free** (every stock trading each month,
   incl. later-delisted); Yahoo was the regression. Correct path:
   (a) ✅ adjust the bhavcopy with a **corporate-actions file** — DONE via
       `scripts/fetch_corporate_actions.py` (yfinance split history → symbol,ex_date,factor);
       loader applies it, fixes #18 WITHOUT dropping dead names. Re-run with `--top-n 500`
       for full coverage (test run used top-120 → ~0.66 WF Sharpe).
   (b) source/build a **point-in-time Nifty 500 (or 200) constituent list** (month-by-month
       membership since ~2010) and map bhavcopy strictly to it — fixes #16/#19 properly,
       reinjecting the dead companies the backtest must hold;
   (c) re-run validation on that clean universe — THEN judge momentum honestly.
   Pause gate-tuning and factor-blending until this is done (per Gemini: "every backtest you
   run is lying to you" until the universe is PiT).
10. **Paper→live** via Paytm Money `pyPMClient` behind a human-confirm switch — ONLY after a
   surviving OOS edge on adjusted, survivorship-free, point-in-time data.
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
