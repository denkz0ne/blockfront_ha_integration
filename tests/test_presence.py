"""Presence classification and cooldown tests."""

from datetime import UTC, datetime, timedelta

from custom_components.blockfront.presence import Presence, PresenceTracker, state_is_active


def test_text_window_match_is_case_insensitive_and_generic_java_is_unknown() -> None:
    assert state_is_active("BlockFront - Match", match="blockfront") is True
    assert state_is_active("javaw.exe", match="blockfront") is False
    assert state_is_active("javaw.exe") is None


def test_presence_uses_cooldown_and_does_not_treat_unknown_as_idle() -> None:
    tracker = PresenceTracker(timedelta(minutes=30))
    now = datetime(2026, 10, 22, tzinfo=UTC)
    assert tracker.update("on", now=now) is Presence.ACTIVE
    assert tracker.update("off", now=now + timedelta(seconds=1)) is Presence.COOLDOWN
    assert tracker.update("unavailable", now=now + timedelta(minutes=10)) is Presence.COOLDOWN
    assert tracker.update("off", now=now + timedelta(minutes=31)) is Presence.INACTIVE
