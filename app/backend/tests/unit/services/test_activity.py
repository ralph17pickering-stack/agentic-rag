from datetime import datetime, timezone, timedelta
import pytest


def test_is_idle_returns_true_when_never_active():
    import app.services.activity as act
    act._last_activity = datetime.min.replace(tzinfo=timezone.utc)
    assert act.is_idle(20) is True


def test_is_idle_returns_false_when_recently_active():
    import app.services.activity as act
    act._last_activity = datetime.now(timezone.utc)
    assert act.is_idle(20) is False


def test_is_idle_returns_true_after_window_passes():
    import app.services.activity as act
    act._last_activity = datetime.now(timezone.utc) - timedelta(minutes=21)
    assert act.is_idle(20) is True


def test_record_activity_updates_timestamp():
    import app.services.activity as act
    before = datetime.now(timezone.utc)
    act.record_activity()
    assert act._last_activity >= before
