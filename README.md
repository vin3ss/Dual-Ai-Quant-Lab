# Dual-AI Quant Lab

A two-part workspace for building **NSE Alpha Forge**, an Indian-equity quant
research engine, using a dual-AI research/build loop.

```
Research/            Strategy research, data catalog, and the dual-AI playbook
nse_alpha_forge/     The engine — modular alpha → portfolio → risk → execution
agents/              Automated multi-agent pipeline (Claude API + OpenAI API)
Backtests/ Models/ Reports/   Outputs
```

## Quick start

```bash
pip install -r requirements.txt

# Run the demo backtest on synthetic data (no API keys, no market data needed)
python -m nse_alpha_forge.backtest.demo

# Run the automated research→design→critique→refine agent loop
cp agents/.env.example agents/.env   # add your ANTHROPIC_API_KEY and OPENAI_API_KEY
python -m agents.run --strategy "cross-sectional momentum"
```

## The two layers

1. **The playbook** (`Research/PromptLibrary/dual_ai_playbook.md`) — how to run the
   research→design→critique→refine loop manually between Claude and ChatGPT.
2. **The automation** (`agents/`) — the same loop wired as a LangGraph state
   machine so it runs without copy-paste.

## NSE Alpha Forge modules

| Module | Status | Purpose |
|---|---|---|
| `alpha/technical` | ✅ working momentum | Price/volume signals |
| `alpha/fundamental` | ✅ working quality | Quality / value / accrual factors |
| `alpha/sentiment` | 🟡 interface stub | News / earnings-call NLP signals |
| `alpha/macro` | 🟡 interface stub | RBI rates, CPI, regime macro |
| `alpha/options` | 🟡 interface stub | OI, PCR, FII derivative positioning |
| `alpha/regime` | 🟡 interface stub | Market-regime detection / gating |
| `portfolio` | ✅ working | Signal blending → target weights |
| `risk` | ✅ working | Vol targeting, caps, drawdown de-risk |
| `backtest` | ✅ working | Vectorized engine + Indian cost model |
| `execution` | 🟡 interface stub | Broker order routing |

Stubs (`🟡`) ship with the real interface defined and a `NotImplementedError`, so
the Builder model (or you) can fill them in without redesigning the contracts.

> **Disclaimer:** Research/educational code. Not investment advice. Backtested or
> hypothetical performance has well-known biases; nothing here is validated for
> live trading.
