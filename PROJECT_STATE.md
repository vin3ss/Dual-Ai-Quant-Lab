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
| alpha | `regime/__init__.py` | 🟠 implemented, NOT wired in | per-date multiplier [0,1]; see open issues |
| alpha | `sentiment/` | 🔴 stub | earnings-call / news NLP |
| alpha | `macro/` | 🔴 stub | RBI/CPI tilts |
| alpha | `options/` | 🔴 stub | OI / PCR / FII-deriv overlay |
| portfolio | `portfolio/constructor.py` | ✅ implemented | signal blend → top-quantile weights |
| risk | `risk/manager.py` | ✅ implemented | caps + vol target + DD de-risk; NO regime hook yet |
| execution | `execution/__init__.py` | 🔴 stub | target broker: Paytm Money Open API (`pyPMClient`) |
| backtest | `backtest/engine.py` | ✅ implemented | vectorized, Indian cost model, shift(1) anti-leakage |
| data | `data/market_data.py` | ✅ synthetic only | real data (nsefin/bhavcopy) not yet connected |

Legend: ✅ done · 🟠 partial / not integrated · 🔴 stub

## Open issues — RegimeDetector (Claude critique, 2026-05-31)

1. **[MED] Frequency mismatch.** Trend/vol windows are in bars (6/12/36) but VIX uses
   `rolling(252, min_periods=60)` and FII `rolling(60/20)` — daily assumptions. Engine
   runs monthly bars, so macro gates sit inert. Fix: one frequency-aware `bars_per_year`
   param, or set macro windows in months.
2. **[MED] Survivorship in fallback index.** Equal-weight synthetic index is built from
   whatever tickers are in `data.prices`; a survivor-only universe leaks hindsight.
   Fix: point-in-time constituents, or document the bias loudly.
3. **[LOW→MED] Hand-tuned magic numbers.** Gate levels + percentile cutoffs are assumed,
   not calibrated. Fix: move to config, reduce DoF, show insensitivity to small changes.
4. **[LOW] Not wired into pipeline.** Nothing consumes the multiplier yet. Fix: add
   `RiskManager.apply_regime(weights, multiplier)` + a test that it shrinks drawdown in a
   synthetic crash, plus a shift-invariance test across all dates (not just last bar).
5. **[LOW] `prices.iloc[0]` base.** NaN at t0 drops a ticker for all history → survivorship
   vector. Fix: normalize by first valid value per column, or build index from returns.

## Roadmap (priority order)

1. **Wire regime into RiskManager** so the multiplier actually scales exposure. ← NEXT
2. **Refine RegimeDetector** per open issues 1–3, 5.
3. **Connect real data** (`nsefin` / bhavcopy) — replace synthetic; enforce point-in-time.
4. **Honest cost & capacity** — validate Indian cost model, add ADV/liquidity limits.
5. **Fill remaining signals** — options flow, sentiment, macro (each critiqued).
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
