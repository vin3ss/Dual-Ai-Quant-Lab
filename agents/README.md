# Automated Dual-AI Pipeline

The manual playbook loop, wired as a [LangGraph](https://langchain-ai.github.io/langgraph/) state machine.

```
research (Claude) → architect (OpenAI) → critic (Claude) → refiner (OpenAI) ↺ → END
```

- **Claude** plays Researcher + Critic (research discovery + adversarial review).
- **OpenAI** plays Architect + Refiner (design + implementation).
- The critic/refiner loop repeats until the critic emits `APPROVED` or `--max-iters` is hit.

## Run

```bash
pip install -r ../requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY and OPENAI_API_KEY
python -m agents.run --strategy "cross-sectional momentum" --max-iters 3
```

Outputs (final design + full transcript) land in `agents/outputs/`.

## Files

| File | Role |
|---|---|
| `graph.py` | State machine: nodes, edges, the critic→refiner loop |
| `llm.py` | Anthropic + OpenAI API wrappers |
| `prompts.py` | System prompts per role (mirror the manual playbook) |
| `run.py` | CLI entry point |

## Extending

- Swap which model plays which role by editing `graph.py` node functions.
- Add a 5th node that calls `nse_alpha_forge.backtest` so the loop ends with a
  real backtest the critic can review (closes the loop end-to-end).
- For more than two models or tool use, the same structure scales — add nodes.

> The critic is intentionally strict (`APPROVED` only when no HIGH issues remain).
> This is the whole point of the second model: catching the bias the first one
> rationalized.
