"""Automated dual-AI quant pipeline.

Wires the manual playbook loop (research -> design -> critique -> refine) into a
LangGraph state machine. Claude plays Researcher + Critic; OpenAI plays
Architect + Refiner. See README.md in this folder.
"""
