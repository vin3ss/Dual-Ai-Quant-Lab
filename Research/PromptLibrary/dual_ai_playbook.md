# Dual-AI Quant Lab — Operating Playbook

A practical playbook for running a two-model research/build loop for **NSE Alpha Forge**.

> **One honest caveat up front.** The "Claude = research, ChatGPT = builder" split is a useful *convention*, not a hard capability boundary. Either model can research, architect, code, and critique. The real value of using two models is **adversarial peer review**: a second model that didn't write the design is more likely to catch the bias/leakage/overfitting that the first one rationalized. Use the split for that reason, not because one model "can't" do the other's job.

---

## 1. Role split (the convention)

| | Model A — Research / Critic | Model B — Architect / Builder |
|---|---|---|
| Suggested model | Claude | ChatGPT |
| Owns | Literature review, data discovery, strategy theory, financial NLP, **adversarial review** of designs and backtests | System architecture, Python implementation, ML pipeline, backtest engine, risk/execution code |
| Output goes to | `Research/`, and critique notes back to Builder | `nse_alpha_forge/`, `Backtests/` |

Swap which model plays which role periodically — whichever model did **not** produce an artifact should be the one that critiques it.

---

## 2. The loop

```
1. RESEARCH   (Model A) → strategy hypothesis + evidence + data plan
2. DESIGN     (Model B) → architecture + module specs
3. CRITIQUE   (Model A) → find bias / leakage / overfitting / capacity issues
4. REFINE     (Model B) → fix the design, implement, backtest
5. REVIEW     (Model A) → read backtest results, challenge the numbers
   → loop back to 4 until the critique stops finding material issues
```

Keep every artifact in this repo so each model can be handed the actual files, not summaries.

---

## 3. Prompt library

Copy-paste these. Replace `{{...}}`. Each is written to produce a *file-ready* artifact.

### A1 — Research a strategy (Model A)
```
You are my quant research lead for Indian (NSE/BSE) equities.
Research the strategy: {{e.g. cross-sectional momentum}}.
Cover: (1) the academic + institutional evidence specific to India,
(2) the concrete recipe (signal definition, lookback, rebalance, neutralization,
risk controls), (3) the data required and where to get it,
(4) the top 5 ways this strategy fails in Indian markets.
Cite sources with links. Flag any claim that comes from a survivorship-biased
or look-ahead-prone backtest. Output as a markdown file I can drop into Research/AlphaIdeas/.
```

### A2 — Discover data sources (Model A)
```
List every usable Indian-market dataset for the strategy "{{strategy}}",
free and paid. For each: what fields it provides, access method, cost,
and its biggest data-quality risk (survivorship, point-in-time, corporate-action
adjustment). Recommend a research stack and a production stack separately.
```

### A3 — Financial NLP (Model A)
```
Here is an earnings-call transcript: {{paste / attach}}.
Extract: management confidence (score 0-100 with justification), changes in
forward guidance vs last quarter, hidden risks, and any hedging language.
Return structured JSON plus a 5-line human summary. Do not invent numbers.
```

### B1 — Turn research into architecture (Model B)
```
Here is the research output: {{paste Research/AlphaIdeas/xyz.md}}.
Design a production Python architecture to implement it inside the package
`nse_alpha_forge`. Produce: module list with responsibilities, data schemas
(pandas/pandera), the signal → portfolio → risk → execution pipeline, and the
public interface (class/function signatures) for each module. No hand-waving —
give real signatures. Respect the existing package layout.
```

### B2 — Implement a module (Model B)
```
Implement `{{module path}}` to the interface we agreed.
Requirements: type hints, docstrings, no look-ahead (all features lagged to
availability date), vectorized pandas, unit tests in tests/. Model Indian
transaction costs (brokerage, STT, exchange, GST, stamp duty, impact cost).
```

### A4 — Adversarial critique (Model A) ← the high-value one
```
Critique this architecture/backtest as a skeptical institutional risk reviewer:
{{paste code or results}}.
Specifically check for: survivorship bias, look-ahead/data leakage, unrealistic
transaction costs, overfitting (degrees of freedom, in-sample tuning), liquidity
/capacity limits, short-selling assumptions, and regime dependence.
For each issue: severity (high/med/low), why it inflates results, and the fix.
Be specific and harsh. Do not praise.
```

### B3 — Refine after critique (Model B)
```
The reviewer found these issues: {{paste critique}}.
Fix the design/code to address each. Show a before/after diff and explain how
each fix changes expected backtest results (usually: lower, more honest Sharpe).
```

---

## 4. Folder map

```
Research/
  AcademicPapers/   papers to read / synthesize
  AlphaIdeas/       strategy write-ups (Model A output)
  Datasets/         data source catalog & notes
  PromptLibrary/    this playbook + saved prompts
nse_alpha_forge/    the engine (Model B output)
agents/             automated version of this loop (Claude API + OpenAI API)
Backtests/          backtest results & tear sheets
Models/             trained model artifacts
Reports/            final reports
```

## 5. When to automate

Run the loop manually until it's stable and you trust the prompts. Then move to
`agents/` — the same loop wired as a LangGraph state machine so research → design
→ critique → refine runs without copy-paste. See `agents/README.md`.
