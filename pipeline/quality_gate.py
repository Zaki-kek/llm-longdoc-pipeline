"""LLM-as-judge quality gate with a bounded revise loop.

Each drafted section is scored by a separate judge call that must answer
``READY`` or ``NEEDS_FIXES: <reasons>``. On ``NEEDS_FIXES`` the section is
re-drafted with the judge feedback, up to ``max_revisions`` times, then the
best available draft is accepted so the pipeline never hangs. A malformed
judge reply is treated as READY (fail-open) rather than blocking the run -
the judge is an improver, not a gatekeeper that can deadlock generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pipeline.llm_client import LLMClient, Message
from pipeline.metrics import Metrics

Verdict = str  # "READY" | "NEEDS_FIXES"


@dataclass
class JudgeResult:
    verdict: Verdict
    reasons: str = ""

    @property
    def ready(self) -> bool:
        return self.verdict == "READY"


def parse_judge(reply: str) -> JudgeResult:
    """Parse a judge reply. Unknown format -> READY (fail-open)."""
    head = reply.strip().splitlines()[0].strip().upper() if reply.strip() else ""
    if head.startswith("NEEDS_FIXES"):
        reasons = reply.strip()[len("NEEDS_FIXES"):].lstrip(": ").strip()
        return JudgeResult("NEEDS_FIXES", reasons)
    return JudgeResult("READY")


def _judge_messages(section: str, text: str, brief_topic: str) -> list[Message]:
    system = (
        "You are a strict editor. Judge whether a document section is complete, "
        "on-topic and internally consistent. Reply with exactly 'READY' or "
        "'NEEDS_FIXES: <short reasons>'. Do not rewrite the text."
    )
    user = (
        f"Topic: {brief_topic}\nSection: {section}\n\n{text}\n\n"
        f"Is this section ready?"
    )
    return [Message("system", system), Message("user", user)]


@dataclass
class QualityGate:
    """Judge a section and drive a bounded revision loop."""

    llm: LLMClient
    max_revisions: int = 2
    metrics: Metrics | None = None

    def judge(self, section: str, text: str, brief_topic: str) -> JudgeResult:
        reply = self.llm.complete(_judge_messages(section, text, brief_topic))
        return parse_judge(reply)

    def ensure(
        self,
        section: str,
        first_draft: str,
        brief_topic: str,
        revise: Callable[[str], str],
    ) -> str:
        """Return an accepted draft, revising up to ``max_revisions`` times.

        ``revise(feedback)`` must produce a new draft given judge feedback.
        Always returns a draft: after the cap the latest draft is accepted so
        the pipeline makes progress instead of looping forever.
        """
        draft = first_draft
        for _ in range(self.max_revisions):
            result = self.judge(section, draft, brief_topic)
            if result.ready:
                return draft
            if self.metrics is not None:
                self.metrics.inc("gate.revisions")
            draft = revise(result.reasons)
        return draft
