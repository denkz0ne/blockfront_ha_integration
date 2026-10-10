"""Independently scheduled data coordinators for BlockFront."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import ApiError, BlockFrontApi, async_fetch_cloud_data, parse_service_status
from .const import DOMAIN, get_update_interval

_LOGGER = logging.getLogger(__name__)
type Fetcher = Callable[[], Awaitable[dict[str, Any]]]


class BlockFrontCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Update one data group while retaining the previous good result on errors."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        name: str,
        interval: timedelta,
        fetcher: Fetcher,
        initial_value: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{name}",
            config_entry=entry,
            update_interval=interval,
            always_update=False,
        )
        self._fetcher = fetcher
        self._initial_value = initial_value
        self._name = name

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the group and keep a timestamped stale value on recoverable errors."""
        attempted_at = datetime.now(UTC).isoformat()
        try:
            value = await self._fetcher()
        except ApiError as err:
            _LOGGER.debug("Unable to refresh %s data: %s", self._name, err)
            previous = dict(self.data or self._initial_value)
            if self._name == "status":
                service_data = dict(previous.get("value", {}))
                service_data["status"] = "unavailable"
                previous["value"] = service_data
            elif self._name == "online":
                cloud_data = dict(previous.get("value", {}))
                cloud_data["polling_status"] = (
                    "rate_limited" if err.status_code == 429 else "unavailable"
                )
                cloud_data["retry_after"] = err.retry_after
                if err.rate_limit:
                    cloud_data["rate_limit"] = err.rate_limit
                cloud_data["api_error"] = str(err)
                previous["value"] = cloud_data
            return {
                **previous,
                "updated_at": previous.get("updated_at"),
                "last_successful_update": previous.get("last_successful_update"),
                "last_attempt": attempted_at,
                "stale": True,
                "last_error": str(err),
            }

        value = dict(value)
        if self._name == "online":
            previous_value = (self.data or {}).get("value", {})
            if value.get("game_player_count") is None and isinstance(previous_value, dict):
                value["game_player_count"] = previous_value.get("game_player_count")
                value["scoreboard_reset_time"] = previous_value.get("scoreboard_reset_time")
                value["cloud_last_successful_update"] = previous_value.get(
                    "cloud_last_successful_update"
                )
            elif value.get("polling_status") == "available":
                value["cloud_last_successful_update"] = attempted_at

        return {
            "value": value,
            "updated_at": attempted_at,
            "last_successful_update": attempted_at,
            "last_attempt": attempted_at,
            "stale": False,
            "last_error": None,
        }


@dataclass(slots=True)
class BlockFrontRuntimeData:
    """Runtime API client and update coordinators for a config entry."""

    api: BlockFrontApi
    coordinators: dict[str, BlockFrontCoordinator]


type BlockFrontConfigEntry = ConfigEntry[BlockFrontRuntimeData]


def create_runtime(
    hass: HomeAssistant, entry: ConfigEntry
) -> BlockFrontRuntimeData:
    """Build an API client and four independently scheduled coordinators."""
    api = BlockFrontApi(async_get_clientsession(hass))
    options = dict(entry.options)

    async def fetch_profile() -> dict[str, Any]:
        return await api.async_get_player(entry.data["player_uuid"])

    async def fetch_matches() -> dict[str, Any]:
        return {"matches": await api.async_get_matches(entry.data["player_uuid"])}

    async def fetch_status() -> dict[str, Any]:
        return parse_service_status(await api.async_get_status())

    coordinators = {
        "profile": BlockFrontCoordinator(
            hass,
            entry,
            "profile",
            get_update_interval(options, "profile"),
            fetch_profile,
            {"value": None},
        ),
        "matches": BlockFrontCoordinator(
            hass,
            entry,
            "matches",
            get_update_interval(options, "matches"),
            fetch_matches,
            {"value": {"matches": []}},
        ),
        "online": BlockFrontCoordinator(
            hass,
            entry,
            "online",
            get_update_interval(options, "online"),
            lambda: async_fetch_cloud_data(api),
            {
                "value": {
                    "online_count": None,
                    "game_player_count": None,
                    "scoreboard_reset_time": None,
                    "source": None,
                    "source_timestamp": None,
                    "api_error": None,
                    "polling_status": "unavailable",
                    "retry_after": None,
                    "rate_limit": {},
                    "cloud_last_successful_update": None,
                }
            },
        ),
        "status": BlockFrontCoordinator(
            hass,
            entry,
            "status",
            get_update_interval(options, "status"),
            fetch_status,
            {
                "value": {
                    "status": "unavailable",
                    "stale_feed_count": 0,
                    "version": None,
                    "uptime_seconds": None,
                    "upstream_error": None,
                }
            },
        ),
    }
    return BlockFrontRuntimeData(api=api, coordinators=coordinators)
