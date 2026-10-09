"""Shared constants for the BlockFront integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "blockfront"
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)

CONF_USERNAME = "username"
CONF_PLAYER_UUID = "player_uuid"

OPTION_PROFILE_INTERVAL = "profile_interval"
OPTION_MATCHES_INTERVAL = "matches_interval"
OPTION_ONLINE_INTERVAL = "online_interval"
OPTION_STATUS_INTERVAL = "status_interval"

DEFAULT_OPTIONS = {
    OPTION_PROFILE_INTERVAL: 900,
    OPTION_MATCHES_INTERVAL: 900,
    OPTION_ONLINE_INTERVAL: 300,
    OPTION_STATUS_INTERVAL: 900,
}

MIN_INTERVALS = {
    OPTION_PROFILE_INTERVAL: 300,
    OPTION_MATCHES_INTERVAL: 300,
    OPTION_ONLINE_INTERVAL: 60,
    OPTION_STATUS_INTERVAL: 300,
}
MAX_INTERVAL_SECONDS = 86_400

UPDATE_INTERVALS = {
    "profile": OPTION_PROFILE_INTERVAL,
    "matches": OPTION_MATCHES_INTERVAL,
    "online": OPTION_ONLINE_INTERVAL,
    "status": OPTION_STATUS_INTERVAL,
}


def get_update_interval(options: dict[str, int], key: str) -> timedelta:
    """Return a validated independent update interval."""
    option_key = UPDATE_INTERVALS[key]
    default = DEFAULT_OPTIONS[option_key]
    minimum = MIN_INTERVALS[option_key]
    seconds = options.get(option_key, default)
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        seconds = default
    return timedelta(seconds=min(max(seconds, minimum), MAX_INTERVAL_SECONDS))
