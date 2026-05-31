# Indian Quant Strategy Review — First Pass

*Research brain output for NSE Alpha Forge. Compiled 2026-05-31. Treat every figure below as a hypothesis to re-test on your own data, not a fact to trade on — most numbers come from author-run backtests with their own universe, costs, and survivorship assumptions.*

---

## 1. What actually works on NSE (evidence summary)

| Factor / strategy | Direction of evidence (India) | Notes & caveats |
|---|---|---|
| **Price momentum (6–12m)** | Strongest and most replicated factor in India | 6-month lookback with quarterly rebalance shows the best risk-adjusted profile in several studies; concentrated in liquid names; FII inflows, P/E and P/B are significant drivers. |
| **Quality (high ROE, low accruals, stable earnings)** | Positive, especially blended with momentum | "Quality-Momentum" combo is the top performer in long-horizon NSE backtests. |
| **Low volatility** | Positive risk-adjusted; shallower drawdowns | Outperforms in crises (2008, 2020); overlaps with quality (low-vol names tend to have stable ROE/EPS). |
| **Value (low P/E, P/B)** | Positive but cyclical and weaker alone | Best used as a blend (Value-Quality), not standalone. |
| **Size (small-cap premium)** | Weak / negative in several Indian studies | Do not assume a clean small-cap premium; liquidity and impact costs eat it. |
| **Statistical arbitrage / cointegrated pairs** | Profitable in sector-neutral large-cap pairs | Needs z-score entry/exit, hard stops (e.g. z > ±3), and transaction-cost modeling; regime breaks are the main risk. |
| **ML / LSTM price prediction** | Mixed; useful for feature extraction, weak as standalone alpha | Walk-forward validation is essential; most published "high accuracy" results leak future data. Treat as a feature generator, not a signal. |
| **Options flow (OI, PCR, FII derivative positioning)** | Used widely as a regime/sentiment overlay | Less peer-reviewed evidence; strongest as a filter on top of a price/factor signal rather than a primary alpha. |

**Practical takeaway for the build:** start with a **Momentum + Quality core, sector-neutralized, volatility-adjusted, monthly (or quarterly) rebalance**, and layer FII/DII flow and options-OI as *regime filters* rather than independent alphas. This is the most defensible starting point given the evidence.

---

## 2. Institutional momentum recipe (the concrete default)

A reasonable, evidence-aligned baseline to implement first:

- **Signal:** 6–12 month total return, skip the most recent 1 month (avoid short-term reversal).
- **Risk adjustment:** divide signal by trailing volatility (or use 12-1 risk-adjusted momentum).
- **Neutralization:** rank within sector (sector-neutral) to avoid unintended sector bets.
- **Construction:** long top quantile, optionally short bottom quantile (long-only is more practical in India due to shorting constraints in cash equities).
- **Rebalance:** monthly or quarterly; quarterly reduces turnover/costs and showed strong risk-adjusted numbers in NSE studies.
- **Risk controls:** position caps, sector caps, volatility targeting at the portfolio level, drawdown-based de-risking.

---

## 3. Known failure modes to design against (the critic's checklist)

These are the things the "Claude critic agent" in the pipeline should hunt for in any architecture or backtest:

1. **Survivorship bias** — use a point-in-time universe (include delisted/merged names). Most free Indian datasets are survivorship-biased by default.
2. **Look-ahead / data leakage** — fundamentals must be lagged to their actual filing/availability date, not the period-end date. Corporate actions (splits/bonus) must be adjusted point-in-time.
3. **Unrealistic costs** — model brokerage, STT, exchange charges, GST, stamp duty, and **impact cost** (especially for mid/small caps). Indian round-trip costs are non-trivial.
4. **Overfitting** — too many factors, tuned thresholds, in-sample Sharpe inflation. Use walk-forward, out-of-sample holdout, and limit degrees of freedom.
5. **Liquidity / capacity** — a strategy that works on ₹1 lakh may be untradeable at ₹10 cr. Track ADV participation.
6. **Regime dependence** — momentum crashes after sharp reversals; pairs break on structural shifts. Stress-test across 2008, 2013 taper, 2018 mid-cap crash, 2020 COVID.
7. **Short-selling assumptions** — cash-segment shorting is restricted intraday; long-short factor backtests that assume free shorting overstate returns.

---

## 4. Sources

Momentum & factors (India):

- [How smart is a momentum strategy? An empirical study of Indian equities (Nigam & Pandey, 2023, SAGE)](https://journals.sagepub.com/doi/10.3233/AF-220399)
- [Momentum, reversals and liquidity: Indian evidence (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23002640)
- [Momentum Factor in Indian Markets: Evidence from the long side (QED Capital PDF)](https://qedcap.com/ast/uploads/2022/03/Momentum-In-India-Sep2021.pdf)
- [Momentum returns: portfolio-based empirical study, Indian market (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0970389617301647)
- [An Index Approach to Factor Investing in India (S&P Dow Jones Indices PDF)](https://www.spglobal.com/spdji/en/documents/research/research-an-index-approach-to-factor-investing-in-india.pdf)
- [Factor Investing India: 18-Year NSE Backtests (BacktestIndia)](https://backtestindia.com/blog/factor-investing-india-complete-guide)
- [Low Volatility Anomaly in India: 18-Year NSE Backtest (BacktestIndia)](https://backtestindia.com/blog/low-volatility-anomaly-india-nse-backtest)
- [NSE Strategy Indices: Which Factors performed best? (Capitalmind)](https://www.capitalmind.in/blog/nse-strategy-indices-factor-investing-basics)

Statistical arbitrage / pairs (India):

- [Cointegrated Pairs Trading in Indian Equity Market 2015–2025 (QuantInsti EPAT)](https://blog.quantinsti.com/cointegrated-pairs-trading-indian-equity-market-epat-project/)
- [Risk-adjusted Returns from Statistical Arbitrage in Indian Stock Futures (Springer, Asia-Pacific Financial Markets)](https://link.springer.com/article/10.1007/s10690-020-09317-1)
- [Designing Efficient Pair-Trading Strategies Using Cointegration for the Indian Market (ResearchGate)](https://www.researchgate.net/publication/365374619_Designing_Efficient_Pair-Trading_Strategies_Using_Cointegration_for_the_Indian_Stock_Market)

ML / deep learning (India):

- [Stock Price Prediction Using ML and LSTM-Based Deep Learning Models (arXiv 2009.10819)](https://arxiv.org/pdf/2009.10819)
- [Analysis of Sectoral Profitability of the Indian Stock Market Using LSTM (arXiv 2111.04976)](https://arxiv.org/pdf/2111.04976)
- [Robust Analysis of Stock Price Time Series Using CNN and LSTM (arXiv 2011.08011)](https://arxiv.org/pdf/2011.08011)
