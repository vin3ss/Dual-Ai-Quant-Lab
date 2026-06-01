# How to Use — NSE Smart Money Radar

A decision-support screen for NSE equities. It combines **price momentum + market
regime + delivery conviction + money-flow + bulk/block deals + live fundamentals &
news** into a per-stock read: **WATCH / CAUTION / AVOID**.

> **It is NOT an auto-trader, a prediction oracle, or financial advice.** It surfaces
> evidence so *you* decide. The underlying momentum edge is modest (~0.4–0.7 Sharpe) and
> survivorship-uncertain. Use it to be disciplined, not to gamble.

---

## 1. Refresh price data (bhavcopy)

Run locally (in your `.venv`). Month-end files are enough for the monthly engine:

```bash
python -m scripts.fetch_bhavcopy --start 2019-01-01 --end 2026-05-31
python -m scripts.fetch_corporate_actions --top-n 500   # split/bonus adjustment
```

Files land in `data_in/bhavcopy/` and `data_in/corporate_actions.csv`.

## 2. Fetch smart-money files

```bash
python -m scripts.fetch_smart_money --start 2025-01-01 --end 2026-05-31
# optional: 6–12 months of bulk/block deal history (slower; run locally)
python -m scripts.fetch_smart_money --start 2025-06-01 --end 2026-05-31 --deals-history
```

Writes `data_in/smartmoney/` (delivery %, bulk/block deals, FII/DII). **Delivery %** is
the dense, reliable signal; bulk/block deals are sparse (blank unless a name had one).

## 3. Run the radar

```bash
python -m scripts.radar --top 12
```

Prints the table and writes **`Reports/radar.html`** — open it in a browser. Related
tools: `scripts.generate_holdings` (target book + chart), `scripts.enrich_holdings`
(detailed per-name view).

## 4. How to read each column

| Column | Meaning | Bullish |
|---|---|---|
| **Mom** | 12-1 momentum strength (z-score) | higher |
| **Flow** | money-flow proxy [-1..1]: up-moves on volume | positive (accumulation) |
| **VolX** | this month's volume ÷ trailing median | >1.5 = unusual activity |
| **Dlv%** | % of volume taken to delivery (conviction, not churn) | ≥ ~45–50% |
| **Deal** | net direction of recent bulk/block deals | BUY |
| **P/E** | trailing price/earnings (live) | not extreme (≲40) |
| **ROE%** | return on equity (live) | higher |
| **News** | crude keyword sentiment of recent headlines | positive |
| **Verdict** | **confluence** of the above | WATCH |

**Market stance** (top of report): RISK-ON / CAUTIOUS / RISK-OFF from the regime model —
when RISK-OFF, the broad market is weak; size down regardless of individual names.

## 5. What NOT to do

- **Do not buy because ONE column is green.** Strong momentum + heavy distribution
  (negative Flow) + sky-high P/E = a trap, not a buy (see how ANANDRATHI flags AVOID).
- **Do not treat verdicts as orders.** WATCH = "look closer," not "buy now."
- **Do not auto-trade it.** There is no execution wired in, by design.
- **Do not bet large.** Modest, unproven edge — position sizes should reflect that.
- **Do not use stale data.** Re-fetch before each review.
- **Do not ignore the market stance.** Buying momentum into a RISK-OFF tape is low-odds.

## 6. Weekly review discipline

1. Refresh data (steps 1–2) once a week (or month-end for the core engine).
2. Run the radar; read the **market stance first**.
3. Shortlist only **WATCH** names with **confluence**: momentum **and** delivery ≥45%
   **and** Flow ≥ 0 **and** reasonable P/E **and** no bad news.
4. Cross-check each shortlisted name yourself (chart, latest news, your own judgement).
5. If you act, do it manually in your broker, small size, and **write down why** — so
   you can review whether the radar actually helped.

---

**The one rule that matters most:**

> Look for **confluence** — momentum + delivery + flow + reasonable valuation + no bad
> news. Never act on a single positive column. This is decision-support, not auto-trading.
