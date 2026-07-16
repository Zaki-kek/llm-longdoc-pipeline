"""Deterministic mock LLM: runs the whole pipeline offline, no key, no cost.

The mock inspects the last user message for a stage hint and returns a fixed,
valid markdown fragment. That makes the smoke test and CI fully deterministic:
same input -> same output, no network, no spend. It satisfies the same
``LLMClient`` protocol as the real backends, so nothing else in the pipeline
knows it is talking to a stub.
"""
from __future__ import annotations

from typing import Sequence

from pipeline.llm_client import Message

_STAGE_STUBS: dict[str, str] = {
    "outline": (
        "## Overview\n## Analysis\n## Data\n## Conclusion\n"
    ),
    "section": (
        "This section develops the point in a few grounded sentences. "
        "It references the brief and stays on topic. "
        "A supporting claim is attributed to a source [1].\n"
    ),
    "judge": "READY\n",
    "readability": (
        "This section develops the point in clear, direct prose. "
        "It stays on topic and attributes a supporting claim to a source [1].\n"
    ),
}


class MockLLM:
    """A stub backend that returns deterministic, stage-appropriate text."""

    name = "mock"

    def __init__(self, stubs: dict[str, str] | None = None) -> None:
        self._stubs = {**_STAGE_STUBS, **(stubs or {})}

    def complete(self, messages: Sequence[Message]) -> str:
        hint = ""
        for m in reversed(messages):
            if m.role == "user":
                hint = m.content.lower()
                break
        for key, text in self._stubs.items():
            if key in hint:
                return text
        # default: a minimal valid section
        return self._stubs["section"]
