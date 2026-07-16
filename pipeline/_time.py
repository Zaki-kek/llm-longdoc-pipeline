"""Timezone-aware time helpers.

All pipeline modules use these helpers for time. A bare ``datetime.now()``
(no timezone) is avoided: it breaks comparisons against stored timestamps and
causes watchdog bugs.
"""
from datetime import datetime, timezone


def now_utc() -> datetime:
    """Current time in UTC, timezone-aware."""
    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Current time as a timezone-aware ISO-8601 string."""
    return now_utc().isoformat()


def seconds_since(ts: datetime) -> float:
    """Seconds elapsed since ``ts`` (timezone-aware comparison)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now_utc() - ts).total_seconds()
