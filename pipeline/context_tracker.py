"""Cross-section consistency: carry a compact summary of prior sections.

A long document drifts when each section is generated in isolation. The
tracker keeps a short, running summary of what earlier sections established
and feeds it into the next section's prompt, so later sections stay
consistent with earlier ones without resending the full document every time.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _first_sentences(text: str, limit: int = 240) -> str:
    """A cheap extractive summary: the opening of a section, trimmed."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > 60 else cut).strip()


@dataclass
class ContextTracker:
    """Accumulates per-section summaries in document order."""

    summaries: list[tuple[str, str]] = field(default_factory=list)

    def add(self, section: str, text: str) -> None:
        self.summaries.append((section, _first_sentences(text)))

    def prior_context(self) -> str:
        """Render the running summary for the next section's prompt."""
        return "\n".join(f"- {name}: {summary}" for name, summary in self.summaries)

    def restore(self, sections: list[dict]) -> None:
        """Rebuild the tracker from persisted section records (auto-resume)."""
        self.summaries = [
            (s["section"], _first_sentences(s.get("text", ""))) for s in sections
        ]
