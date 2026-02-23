"""In-memory idle detection — tracks last HTTP request timestamp."""
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
