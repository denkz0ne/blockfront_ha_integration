"""Resolve Home Assistant state into conservative BlockFront play presence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum


class Presence(StrEnum):
    """Presence confidence state used by adaptive collection."""

    ACTIVE = "active"
    COOLDOWN = "cooldown"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


def state_is_active(state: str, *, match: str = "") -> bool | None:
    """Interpret a binary sensor or a configured active-window text sensor."""
    value = state.strip().casefold()
    if value in {"unavailable", "unknown", "none", ""}:
        return None
    if value in {"on", "playing", "true", "active"}:
        return True
    if value in {"off", "false", "idle", "inactive"}:
        return False
    if match.strip():
        return match.strip().casefold() in value
    return None


class PresenceTracker:
    """Track transitions and retain an activity cooldown window."""

    def __init__(self, cooldown: timedelta) -> None:
        self.cooldown = cooldown
        self.last_active: datetime | None = None

    def update(self, state: str, *, match: str = "", now: datetime | None = None) -> Presence:
        """Record state and return current activity confidence."""
        now = now or datetime.now(UTC)
        active = state_is_active(state, match=match)
        if active is True:
            self.last_active = now
            return Presence.ACTIVE
        if active is None:
            if self.last_active and now - self.last_active < self.cooldown:
                return Presence.COOLDOWN
            return Presence.UNKNOWN
        if self.last_active and now - self.last_active < self.cooldown:
            return Presence.COOLDOWN
        return Presence.INACTIVE
