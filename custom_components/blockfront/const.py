"""Shared constants for the BlockFront integration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.const import Platform

DOMAIN = "blockfront"
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON)

CONF_USERNAME = "username"
CONF_PLAYER_UUID = "player_uuid"
CONF_API_BASE_URL = "api_base_url"
CONF_API_KEY = "api_key"
OPTION_PROFILE_SOURCE = "profile_source"
OPTION_MATCHES_SOURCE = "matches_source"
SOURCE_BLOCKLYTICS = "blocklytics"
SOURCE_COMMUNITY = "community"
OPTION_COMMUNITY_API_BASE_URL = "community_api_base_url"
DEFAULT_COMMUNITY_API_BASE_URL = "https://blockfrontapi.vuis.dev/api/v1/"

OPTION_PROFILE_INTERVAL = "profile_interval"
OPTION_MATCHES_INTERVAL = "matches_interval"
OPTION_ONLINE_INTERVAL = "online_interval"
OPTION_STATUS_INTERVAL = "status_interval"
OPTION_ANALYTICS_INTERVAL = "analytics_interval"
OPTION_HISTORY_INTERVAL = "history_interval"
OPTION_ARCHIVE_INTERVAL = "archive_interval"
OPTION_GLOBAL_INTERVAL = "global_interval"
OPTION_ACTIVITY_ENTITY = "activity_entity"
OPTION_ACTIVITY_MATCH = "activity_match"
OPTION_ACTIVITY_COOLDOWN = "activity_cooldown_minutes"
OPTION_IDLE_HEARTBEAT = "idle_heartbeat_minutes"
OPTION_ADAPTIVE_POLLING = "adaptive_polling"
OPTION_ADAPTIVE_MARGIN = "adaptive_margin_percent"
OPTION_PRESENCE_MODE = "presence_mode"

DEFAULT_OPTIONS: dict[str, int | str] = {
    OPTION_PROFILE_SOURCE: SOURCE_COMMUNITY,
    OPTION_MATCHES_SOURCE: SOURCE_COMMUNITY,
    OPTION_ANALYTICS_INTERVAL: 1800,
    OPTION_HISTORY_INTERVAL: 3600,
    OPTION_ARCHIVE_INTERVAL: 21600,
    OPTION_GLOBAL_INTERVAL: 3600,
    OPTION_PROFILE_INTERVAL: 900,
    OPTION_MATCHES_INTERVAL: 900,
    OPTION_ONLINE_INTERVAL: 300,
    OPTION_STATUS_INTERVAL: 900,
    OPTION_ACTIVITY_ENTITY: "",
    OPTION_ACTIVITY_MATCH: "BlockFront",
    OPTION_ACTIVITY_COOLDOWN: 30,
    OPTION_IDLE_HEARTBEAT: 60,
    OPTION_ADAPTIVE_POLLING: True,
    OPTION_ADAPTIVE_MARGIN: 10,
    OPTION_PRESENCE_MODE: "auto",
}

MIN_INTERVALS = {
    OPTION_ANALYTICS_INTERVAL: 900,
    OPTION_HISTORY_INTERVAL: 1800,
    OPTION_ARCHIVE_INTERVAL: 3600,
    OPTION_GLOBAL_INTERVAL: 1800,
    OPTION_PROFILE_INTERVAL: 300,
    OPTION_MATCHES_INTERVAL: 300,
    OPTION_ONLINE_INTERVAL: 60,
    OPTION_STATUS_INTERVAL: 300,
}
MAX_INTERVAL_SECONDS = 86_400

UPDATE_INTERVALS = {
    "analytics": OPTION_ANALYTICS_INTERVAL,
    "history": OPTION_HISTORY_INTERVAL,
    "archive": OPTION_ARCHIVE_INTERVAL,
    "global": OPTION_GLOBAL_INTERVAL,
    "profile": OPTION_PROFILE_INTERVAL,
    "matches": OPTION_MATCHES_INTERVAL,
    "online": OPTION_ONLINE_INTERVAL,
    "status": OPTION_STATUS_INTERVAL,
}


def get_update_interval(options: Mapping[str, Any], key: str) -> timedelta:
    """Return a validated independent update interval."""
    option_key = UPDATE_INTERVALS[key]
    default = DEFAULT_OPTIONS[option_key]
    minimum = MIN_INTERVALS[option_key]
    seconds = options.get(option_key, default)
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        seconds = default
    return timedelta(seconds=min(max(seconds, minimum), MAX_INTERVAL_SECONDS))
