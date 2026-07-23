"""Content-hash dedup/cache of LLM calls.

Long-document runs re-issue near-identical prompts (judge, revise, polish).
Caching by a content fingerprint of the messages avoids paying for the same
call twice and makes re-runs cheaper and more deterministic. Two pieces:

- ``CachingClient`` wraps any ``LLMClient`` and memoises completions in a
  ``MutableMapping`` (an in-memory ``dict`` by default).
- ``FileCache`` is a crash-safe persistent backing store: one JSON file
  written via the existing atomic ``temp+rename`` helper, so a cache survives
  a restart and never leaves a half-written file.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.atomic_write import atomic_write_json
from pipeline.llm_client import LLMClient, Message
from pipeline.metrics import Metrics


def messages_fingerprint(messages: Sequence[Message]) -> str:
    """Stable sha256 over the (role, content) pairs of ``messages``."""
    canon = json.dumps(
        [[m.role, m.content] for m in messages],
        ensure_ascii=True,
        sort_keys=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class CachingClient:
    """Memoise completions of ``inner`` keyed by the message fingerprint."""

    inner: LLMClient
    store: MutableMapping[str, str] = field(default_factory=dict)
    name: str = "cached"
    metrics: Metrics | None = None

    def complete(self, messages: Sequence[Message]) -> str:
        key = messages_fingerprint(messages)
        if key in self.store:
            if self.metrics is not None:
                self.metrics.inc("cache.hit")
            return self.store[key]
        value = self.inner.complete(messages)
        self.store[key] = value
        if self.metrics is not None:
            self.metrics.inc("cache.miss")
        return value


class FileCache(MutableMapping[str, str]):
    """A ``MutableMapping`` persisted to one JSON file (crash-safe writes)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._data: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._data is None:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            else:
                self._data = {}
        return self._data

    def _flush(self) -> None:
        atomic_write_json(self._path, dict(self._load()))

    def __getitem__(self, key: str) -> str:
        return self._load()[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._load()[key] = value
        self._flush()

    def __delitem__(self, key: str) -> None:
        del self._load()[key]
        self._flush()

    def __iter__(self) -> Iterator[str]:
        return iter(self._load())

    def __len__(self) -> int:
        return len(self._load())
