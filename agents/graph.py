"""LangGraph state machine for the dual-AI quant loop.

    research (Claude) -> architect (OpenAI) -> critic (Claude)
                              ^                      |
                              |                      v
                          refiner (OpenAI) <--- needs work?
                                                     |
                                                  approved / max iters -> END

Claude = Researcher + Critic.  OpenAI = Architect + Refiner.
The critic/refiner loop repeats until the critic emits APPROVED or max_iterations.
"""

from __future__ import annotations
from typing import TypedDict
import datetime as dt

from langgraph.graph import StateGraph, END

from .llm import call_claude, call_openai
from . import prompts


class QuantState(TypedDict, total=False):
    strategy: str
    research: str
    design: str
    critique: str
    iteration: int
    max_iterations: int
    approved: bool
    transcript: list


def _log(state: QuantState, role: str, text: str) -> None:
    state.setdefault("transcript", []).append(
        {"ts": dt.datetime.now().isoformat(timespec="seconds"),
         "role": role, "text": text}
    )


# --- nodes ----------------------------------------------------------------
def research_node(state: QuantState) -> QuantState:
    out = call_claude(prompts.RESEARCHER, f"Strategy to research: {state['strategy']}")
    _log(state, "researcher (claude)", out)
    return {"research": out}


def architect_node(state: QuantState) -> QuantState:
    user = f"Research findings:\n\n{state['research']}\n\nDesign the architecture."
    out = call_openai(prompts.ARCHITECT, user)
    _log(state, "architect (openai)", out)
    return {"design": out, "iteration": 0}


def critic_node(state: QuantState) -> QuantState:
    user = (f"Strategy: {state['strategy']}\n\nResearch:\n{state['research']}\n\n"
            f"Design under review:\n{state['design']}")
    out = call_claude(prompts.CRITIC, user)
    approved = any(line.strip() == "APPROVED" for line in out.splitlines())
    _log(state, "critic (claude)", out)
    return {"critique": out, "approved": approved}


def refiner_node(state: QuantState) -> QuantState:
    user = (f"Current design:\n{state['design']}\n\n"
            f"Reviewer critique:\n{state['critique']}\n\nRevise the full design.")
    out = call_openai(prompts.REFINER, user)
    _log(state, "refiner (openai)", out)
    return {"design": out, "iteration": state.get("iteration", 0) + 1}


def route_after_critique(state: QuantState) -> str:
    if state.get("approved"):
        return END
    if state.get("iteration", 0) >= state.get("max_iterations", 3):
        return END
    return "refiner"


# --- assembly --------------------------------------------------------------
def build_graph():
    g = StateGraph(QuantState)
    g.add_node("research", research_node)
    g.add_node("architect", architect_node)
    g.add_node("critic", critic_node)
    g.add_node("refiner", refiner_node)

    g.set_entry_point("research")
    g.add_edge("research", "architect")
    g.add_edge("architect", "critic")
    g.add_conditional_edges("critic", route_after_critique,
                            {"refiner": "refiner", END: END})
    g.add_edge("refiner", "critic")
    return g.compile()
