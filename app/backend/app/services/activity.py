"""In-memory idle detection — tracks last HTTP request timestamp.

NOTE: This implementation is process-local. In multi-worker deployments
(uvicorn --workers N > 1), each worker maintains its own independent
timestamp. The enrichment sweep may run in one worker while another is
actively serving requests. For single-worker deployments this is correct.
"""
from datetime import datetime, timezone, timedelta

_last_activity: datetime = datetime.min.replace(tzinfo=timezone.utc)


def record_activity() -> None:
    """Call on every incoming HTTP request."""
    global _last_activity
    _last_activity = datetime.now(timezone.utc)


def is_idle(minutes: float) -> bool:
    """Return True if no activity has been recorded in the last `minutes`."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return _last_activity < threshold
