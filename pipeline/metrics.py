"""Thread-safe in-process metrics: counters + timings, no external deps.

A tiny observability primitive the pipeline threads through its LLM,
fallback, quality-gate and orchestration paths. It is deliberately
dependency-free (no Prometheus client) so it runs in CI and in a container
with nothing installed; a ``snapshot()`` of the accumulated numbers is
surfaced on the run ``Result``. All mutation is guarded by a lock so it is
safe under the concurrent section/fallback paths.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """Accumulate named counters and timing samples under a lock."""

    _counters: dict[str, int] = field(default_factory=dict)
    _timings: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, name: str, k: int = 1) -> None:
        """Increment counter ``name`` by ``k`` (default 1)."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + k

    def observe(self, name: str, seconds: float) -> None:
        """Record a timing sample (seconds) under ``name``."""
        with self._lock:
            self._timings.setdefault(name, []).append(seconds)

    def snapshot(self) -> dict:
        """Return a JSON-friendly copy of the current counters and timings."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timings": {
                    n: {"count": len(v), "total": sum(v)}
                    for n, v in self._timings.items()
                },
            }
