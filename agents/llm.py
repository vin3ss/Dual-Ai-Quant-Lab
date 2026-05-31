"""Thin wrappers around the Anthropic and OpenAI chat APIs.

Kept deliberately small so the graph logic stays readable. Both functions take a
system prompt + user prompt and return text.
"""

from __future__ import annotations
import os


def _env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if not val:
        raise RuntimeError(
            f"Missing {name}. Copy agents/.env.example to agents/.env and fill it in."
        )
    return val


def call_claude(system: str, user: str, *, max_tokens: int = 4000) -> str:
    """Anthropic Messages API. Used for the Researcher and Critic roles."""
    from anthropic import Anthropic

    client = Anthropic(api_key=_env("ANTHROPIC_API_KEY"))
    model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def call_openai(system: str, user: str, *, max_tokens: int = 4000) -> str:
    """OpenAI Chat Completions API. Used for the Architect and Refiner roles."""
    from openai import OpenAI

    client = OpenAI(api_key=_env("OPENAI_API_KEY"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""
