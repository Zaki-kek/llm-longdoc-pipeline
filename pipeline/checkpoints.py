"""Substep-aware job state store.

Per-job state file (state.json):
    stages: {
        "stage1": {
            "status": "done|running|pending|error",
            "substeps": {
                "state": "done",
                "registry": "done",
                "content": "running"
            },
            "started_at": "ISO-8601",
            "completed_at": "ISO-8601 | null",
        },
        ...
    }
    sessions: {
        "draft1": {
            "uuid": "...",
            "type": "draft",
            "stage": 1,
            "last_activity_ts": "ISO-8601"
        },
        ...
    }

Guarantees:
- atomic writes via temp+rename (same filesystem)
- patch-based writes — merge + rewrite atomically
- fcntl as a secondary guard against concurrent writers
"""
import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pipeline._time import iso_now
from pipeline.atomic_write import (
    atomic_write_json as _atomic_write,
    atomic_write_text,
)

__all__ = ["atomic_write_text"]

STATE_FILENAME = "state.json"
BACKUPS_DIR = "_state_backups"
MAX_BACKUPS = 10


def _state_path(job_dir: Path) -> Path:
    return job_dir / STATE_FILENAME


def _backup_state(job_dir: Path, state: dict) -> None:
    """Rotating backups in _state_backups/."""
    backups_dir = job_dir / BACKUPS_DIR
    backups_dir.mkdir(exist_ok=True)
    step = state.get("last_step", 0)
    ts = int(__import__("time").time())
    backup_path = backups_dir / f"state_step{step}_{ts}.json"
    backup_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    # rotation
    backups = sorted(backups_dir.glob("state_*.json"))
    while len(backups) > MAX_BACKUPS:
        backups[0].unlink()
        backups.pop(0)


def read_state(job_dir: Path) -> dict:
    """Read state. A non-existing file yields an empty dict.

    Auto-repairs on JSONDecodeError: tries safe_read_state (fallback to
    backups). On successful recovery, rewrites the main file with the
    recovered JSON so later writes do not break.

    Guard against externally-initiated corruption (a process
    writing malformed JSON over the existing state).
    """
    p = _state_path(job_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        import logging
        log = logging.getLogger(__name__)
        log.error(f"State corrupted at {p}: {e}. Attempting auto-repair from backups.")
        try:
            from pipeline._recovery import safe_read_state as _safe
            data = _safe(job_dir)
            if data:
                # atomic rewrite of the main file with recovered data
                _atomic_write(p, data)
                log.warning(f"State auto-repaired from backup (last_step={data.get('last_step', '?')})")
                return data
        except Exception as rec_err:
            log.error(f"Auto-repair failed: {rec_err}")
        return {}


def write_state(job_dir: Path, state: dict, backup: bool = True) -> None:
    """Atomic write with a backup and an fcntl lock."""
    target = _state_path(job_dir)
    if backup and target.exists():
        try:
            _backup_state(job_dir, read_state(job_dir))
        except Exception:
            # Don't block main write on backup failure
            pass

    # fcntl lock via a separate lock file
    lock_path = target.parent / f".{STATE_FILENAME}.lock"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            _atomic_write(target, state)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def _deep_set(d: dict, path: list[str], value: Any) -> None:
    """Recursively set a value at path, e.g. ['stages', 'stage1', 'status'] -> value."""
    current = d
    for key in path[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


@contextmanager
def state_locked(job_dir: Path, backup: bool = True) -> Iterator[dict]:
    """read-modify-write helper holding fcntl LOCK_EX from read to write.

    Yields the current state dict; mutations made inside the ``with``
    block are atomically written back on clean exit. If the block raises,
    no write happens and the on-disk state is untouched.

    Closes the race in helpers like ``touch_session_activity`` that used
    ``read_state`` outside the patch lock and then patched with a stale
    full-session dict, overwriting any concurrent updates that landed
    between read and write.

    Args:
        job_dir: job directory containing state.json.
        backup: rotate a backup before writing (default True), matching
            ``write_state_patch`` semantics.

    Example:
        with state_locked(job_dir) as p:
            p["sessions"]["s1"]["last_activity_ts"] = iso_now()
            # auto-write on exit
    """
    target = _state_path(job_dir)
    lock_path = target.parent / f".{STATE_FILENAME}.lock"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            current = read_state(job_dir)
            if backup and current:
                try:
                    _backup_state(job_dir, current)
                except Exception:
                    # Don't block main write on backup failure (parity
                    # with write_state / write_state_patch).
                    pass
            yield current
            # Only reached on clean exit — exceptions skip the write so
            # callers never persist a partially-mutated state.
            _atomic_write(target, current)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def write_state_patch(job_dir: Path, patch: dict[str, Any], backup: bool = True) -> dict:
    """Patch-based write for race-safe independent field updates.

    Args:
        patch: dict of dotted keys. Example: {"sessions.draft1": {"uuid": "..."}}
        backup: rotate a backup before writing (default True) so auto-repair
            has a source to recover from.

    Returns:
        The updated state.
    """
    target = _state_path(job_dir)
    lock_path = target.parent / f".{STATE_FILENAME}.lock"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            # read_state auto-repairs on corruption (safe_read_state fallback)
            current = read_state(job_dir)
            # back up before applying the patch - the source for later auto-repair
            if backup and current:
                try:
                    _backup_state(job_dir, current)
                except Exception:
                    pass
            for dotted_key, value in patch.items():
                _deep_set(current, dotted_key.split("."), value)
            _atomic_write(target, current)
            return current
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def record_session(
    job_dir: Path,
    key: str,
    uuid_value: str,
    session_type: str,
    stage: int,
) -> dict:
    """Record a resumable session id with a type tag.

    Args:
        key: short session name in state (e.g. 'draft', 'review').
        uuid_value: the session identifier to resume later.
        session_type: e.g. 'draft' | 'review' | 'revise'.
        stage: stage number this session belongs to.
    """
    entry = {
        "uuid": uuid_value,
        "type": session_type,
        "stage": stage,
        "last_activity_ts": iso_now(),
    }
    return write_state_patch(job_dir, {f"sessions.{key}": entry})


def touch_session_activity(job_dir: Path, key: str) -> None:
    """Refresh last_activity_ts (for orphaned-session detection).

    read and write happen under a single fcntl LOCK_EX via state_locked,
    so a competing writer cannot slip between read and write and be
    overwritten by a full session dict from an old snapshot.
    """
    with state_locked(job_dir) as p:
        sessions = p.get("sessions")
        if not sessions or key not in sessions:
            return
        sessions[key]["last_activity_ts"] = iso_now()


def get_session(
    job_dir: Path, key: str, expected_type: str | None = None
) -> dict | None:
    """Read a session by key, optionally validating its type.

    Returns:
        None if the session is absent; the dict if found.

    Raises:
        ValueError: on type mismatch (expected_type given and != actual).
    """
    state = read_state(job_dir)
    session = state.get("sessions", {}).get(key)
    if session is None:
        return None
    if expected_type is not None and session.get("type") != expected_type:
        raise ValueError(
            f"Session type mismatch for {key!r}: expected {expected_type!r}, "
            f"got {session.get('type')!r}"
        )
    return session


def mark_substep(
    job_dir: Path,
    stage: str,
    substep: str,
    status: str,
    extra: dict | None = None,
) -> None:
    """Update substep status at stages.{stage}.substeps.{substep}."""
    patch = {f"stages.{stage}.substeps.{substep}": status}
    if extra:
        for k, v in extra.items():
            patch[f"stages.{stage}.{k}"] = v
    write_state_patch(job_dir, patch)


def mark_substep_done(
    job_dir: Path,
    stage: str,
    substep: str,
    last_step: int,
    extra: dict | None = None,
) -> None:
    """atomic ``substeps[X] = "done"`` + ``last_step = N`` write.

    Pre-fix: ``mark_substep`` and ``write_state_patch({"last_step": N})``
    were two separate fcntl-locked writes. A crash between them left
    ``substeps[X] = "done"`` while ``last_step`` still pointed at the
    previous step — AUTO-RESUME re-ran the already-completed step and
    repeated any non-idempotent side effects (external calls, writes).

    Post-fix: a single ``state_locked`` block updates substep status,
    optional extras (``completed_at`` etc.), and ``last_step`` together;
    one atomic write, no crash window.
    """
    with state_locked(job_dir) as p:
        stages = p.setdefault("stages", {})
        stage_entry = stages.setdefault(stage, {})
        substeps = stage_entry.setdefault("substeps", {})
        substeps[substep] = "done"
        if extra:
            for k, v in extra.items():
                stage_entry[k] = v
        p["last_step"] = last_step
