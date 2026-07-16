"""Final readability pass: trim filler and tighten prose.

An editorial quality step. It removes empty filler phrases and asks the model to
tighten wording while preserving every fact, claim and citation marker [n]. Its
only objective is that the text reads clearly.
"""
from __future__ import annotations

import re

from pipeline.llm_client import LLMClient, Message

# Common filler phrases that add words without meaning.
_FILLER = [
    r"\bit is important to note that\b",
    r"\bit is worth noting that\b",
    r"\bit should be noted that\b",
    r"\bneedless to say,?\b",
    r"\bin today's world\b",
    r"\bat the end of the day,?\b",
    r"\bwhen it comes to\b",
]


def strip_filler(text: str) -> str:
    """Remove a small set of well-known filler phrases (deterministic)."""
    out = text
    for pat in _FILLER:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    # de-capitalize a leftover sentence start only if it clearly dangles
    return out.strip()


def _editor_messages(text: str) -> list[Message]:
    system = (
        "You are a copy editor. Tighten the text so it reads clearly and "
        "directly: cut filler and empty intensifiers, keep every fact, claim "
        "and citation marker [n] unchanged. Return only the edited text."
    )
    return [Message("system", system), Message("user", text)]


def polish(text: str, llm: LLMClient | None = None) -> str:
    """Deterministic filler-strip, then an optional LLM tightening pass."""
    cleaned = strip_filler(text)
    if llm is None:
        return cleaned
    return llm.complete(_editor_messages(cleaned))
