"""Deterministic long-input chunking with boundary snapping + context budgeting.

Feeding an over-long source into a fixed-context model needs a clean split.
This module is a PURE, network-free partition of the input over character
offsets. Cuts are SNAPPED back to a nearby paragraph or sentence boundary so
chunks read naturally, yet the split stays contiguous: every character is
emitted, adjacent chunks overlap by exactly ``overlap`` characters, and the
reconstruct-minus-overlap invariant holds::

    chunk[0] + "".join(c[overlap:] for c in chunk[1:]) == text

``overlap`` is constrained to ``<= max_chars // 2`` so the snapped window
(minimum fill ``max_chars // 2``) always advances the cursor - a larger
overlap can stall a naive windowed walk.
"""
from __future__ import annotations

from typing import Sequence


def chunk_text(text: str, max_chars: int, overlap: int = 0) -> list[str]:
    """Split ``text`` into boundary-snapped chunks of at most ``max_chars``.

    Args:
        text: The input to partition.
        max_chars: Maximum length of any chunk (> 0).
        overlap: Characters each chunk after the first repeats from the prior
            chunk's tail. Must satisfy ``0 <= overlap <= max_chars // 2``.

    Returns:
        The chunks, in order, satisfying the reconstruct-minus-overlap
        invariant. For ``overlap == 0`` this reduces to ``"".join(chunks) ==
        text``.

    Raises:
        ValueError: If ``max_chars <= 0`` or the overlap bound is violated.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")
    if not (0 <= overlap <= max_chars // 2):
        raise ValueError("overlap must satisfy 0 <= overlap <= max_chars // 2")
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    i = 0
    n = len(text)
    floor = max_chars // 2
    while i < n:
        window_end = min(i + max_chars, n)
        end = window_end
        if window_end < n:  # snap only interior cuts; the last window is exact
            region_start = i + floor  # minimum fill before a cut is allowed
            snap = -1
            para = text.rfind("\n\n", region_start, window_end)
            if para != -1:
                snap = para + 2
            else:
                sent = text.rfind(". ", region_start, window_end)
                if sent != -1:
                    snap = sent + 2
            if snap != -1 and snap > i:
                end = snap
        chunks.append(text[i:end])
        if end >= n:
            break
        i = end - overlap  # overlap <= floor guarantees this advances
    return chunks


def pack_context(entries: Sequence[str], budget_chars: int) -> str:
    """Join the most recent ``entries`` (newest last) within ``budget_chars``.

    Walks entries from the tail so the freshest context is always retained,
    dropping older entries once the budget would be exceeded. The returned
    string never exceeds ``budget_chars``.
    """
    if budget_chars <= 0:
        return ""
    kept: list[str] = []
    total = 0
    sep = "\n"
    for entry in reversed(entries):
        extra = len(entry) + (len(sep) if kept else 0)
        if total + extra > budget_chars and kept:
            break  # keep at least the newest entry, even if it alone overflows
        kept.append(entry)
        total += extra
    kept.reverse()
    out = sep.join(kept)
    return out[-budget_chars:]
