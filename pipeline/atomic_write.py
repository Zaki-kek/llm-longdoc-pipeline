"""Atomic filesystem writes: temp-file + rename on the same filesystem.

A rename within one filesystem is atomic, so a reader either sees the old
file or the fully-written new one, never a partial write. This is the
foundation the checkpoint store relies on to survive a crash mid-write.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Atomically write ``data`` to ``target`` via a same-fs temp file.

    On any failure the temp fragment is cleaned up before re-raising, so a
    disk-full / OSError mid-write cannot leave orphan ``.tmp`` files that
    accumulate and exhaust inodes on a long-running system.
    """
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        tmp.write_bytes(data)
        tmp.rename(target)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # Best-effort cleanup; do not mask the original failure.
            pass
        raise


def atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    """Atomically write a dict as pretty UTF-8 JSON."""
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_write_bytes(target, payload)


def atomic_write_text(target: Path, text: str, encoding: str = "utf-8") -> None:
    """Atomically write a text artifact (same temp+rename guarantee)."""
    atomic_write_bytes(target, text.encode(encoding))
