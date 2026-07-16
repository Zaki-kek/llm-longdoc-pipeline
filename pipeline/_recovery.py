"""State-file recovery: corruption-safe read with backup fallback.

``safe_read_state`` reads a job's ``state.json`` and, on ``JSONDecodeError``,
falls back to the most recent valid snapshot in ``_state_backups/`` and
atomically restores the main file from it. This keeps a mid-write crash from
turning a half-written state file into a permanent source of corruption.
"""
import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)

STATE_FILENAME = "state.json"


def safe_read_state(job_dir: Path) -> dict:
    """Read ``state.json`` with a fallback to backups on corruption."""
    state_path = job_dir / STATE_FILENAME
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error(
            f"State corrupted at {state_path}: {e}. "
            f"Attempting recovery from _state_backups/."
        )
        return _recover_from_backup(job_dir, state_path)


def _atomic_write_text(path: Path, text: str) -> None:
    """tmp + os.replace on the same filesystem.

    Guards against a half-written file if the process crashes mid-copy: the
    target either points at the old file or the new valid one, never a partial.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _recover_from_backup(job_dir: Path, main_path: Path) -> dict:
    """Restore from the most recent valid backup, atomically."""
    backups_dir = job_dir / "_state_backups"
    if not backups_dir.exists():
        logger.critical(f"No backups dir at {backups_dir} - state unrecoverable")
        return {}

    backups = sorted(backups_dir.glob("state_*.json"), reverse=True)
    for backup in backups:
        try:
            backup_text = backup.read_text(encoding="utf-8")
            data = json.loads(backup_text)
            logger.warning(
                f"Recovered state from backup {backup.name} "
                f"(last_step={data.get('last_step', 'unknown')})"
            )
            _atomic_write_text(main_path, backup_text)
            return data
        except json.JSONDecodeError:
            logger.warning(f"Backup {backup.name} also corrupted, trying next")
            continue

    logger.critical(f"All {len(backups)} backups corrupted for {main_path}")
    return {}
