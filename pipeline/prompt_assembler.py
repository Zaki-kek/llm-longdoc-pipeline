"""Composable prompts from independent axes: document_type x tone x source.

Instead of one giant hardcoded prompt per document kind, the assembler builds
a system prompt by composing small, independent fragments. Adding a new
document type or tone is a data change (one fragment), not a prompt rewrite.
This keeps prompts testable and diff-able and avoids copy-paste drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from pipeline.llm_client import Message

# --- Axis fragments (data, not code paths) ---------------------------------

_DOCUMENT_TYPE: dict[str, str] = {
    "report": "You write structured analytical reports with clear sections.",
    "brief": "You write concise decision briefs: context, options, recommendation.",
    "spec": "You write precise technical specifications with unambiguous requirements.",
}

_TONE: dict[str, str] = {
    "neutral": "Keep the tone neutral and factual.",
    "formal": "Keep the tone formal and precise.",
    "plain": "Prefer plain, direct language over jargon.",
}

_SOURCE: dict[str, str] = {
    "grounded": "Ground claims in the provided sources and cite them as [n].",
    "none": "Do not invent citations; write from the brief only.",
}


@dataclass
class Brief:
    """One generation job: what document, about what, in which style."""

    topic: str
    document_type: str = "report"
    tone: str = "neutral"
    source: str = "none"
    sections: list[str] = field(default_factory=lambda: ["Overview", "Analysis", "Data", "Conclusion"])
    sources: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        return cls(
            topic=d["topic"],
            document_type=d.get("document_type", "report"),
            tone=d.get("tone", "neutral"),
            source=d.get("source", "none"),
            sections=list(d.get("sections", ["Overview", "Analysis", "Data", "Conclusion"])),
            sources=list(d.get("sources", [])),
        )


def _system_prompt(brief: Brief) -> str:
    parts = [
        _DOCUMENT_TYPE.get(brief.document_type, _DOCUMENT_TYPE["report"]),
        _TONE.get(brief.tone, _TONE["neutral"]),
        _SOURCE.get(brief.source, _SOURCE["none"]),
    ]
    return " ".join(parts)


def outline_messages(brief: Brief) -> list[Message]:
    """Prompt to produce an outline (H2 headings) for the document."""
    user = (
        f"Produce an outline for a {brief.document_type} on: {brief.topic}. "
        f"Return only H2 markdown headings (## ...), one per intended section."
    )
    return [Message("system", _system_prompt(brief)), Message("user", user)]


def section_messages(brief: Brief, section: str, prior_context: str) -> list[Message]:
    """Prompt to draft one section, given a summary of prior sections."""
    src = ""
    if brief.sources and brief.source == "grounded":
        listed = "\n".join(f"[{i + 1}] {s}" for i, s in enumerate(brief.sources))
        src = f"\nSources you may cite as [n]:\n{listed}\n"
    ctx = f"\nSo far the document covered:\n{prior_context}\n" if prior_context else ""
    user = (
        f"Write the section '{section}' of a {brief.document_type} on: {brief.topic}."
        f"{ctx}{src}\nWrite the section body only, no heading. Stay consistent with prior sections."
    )
    return [Message("system", _system_prompt(brief)), Message("user", user)]


def known_axes() -> dict[str, Sequence[str]]:
    """Introspection helper (used by tests and docs)."""
    return {
        "document_type": tuple(_DOCUMENT_TYPE),
        "tone": tuple(_TONE),
        "source": tuple(_SOURCE),
    }
