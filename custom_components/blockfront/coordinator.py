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
from .const import CONF_API_BASE_URL, CONF_API_KEY, DOMAIN, get_update_interval

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
                service_data["api_polling_status"] = (
                    "rate_limited" if err.status_code == 429 else "unavailable"
                )
                service_data["api_last_error"] = str(err)
                service_data["api_last_attempt"] = attempted_at
                service_data["api_rate_limit_remaining"] = None
                service_data["api_retry_after"] = err.retry_after
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
        if self._name == "archive":
            # A failed optional archive endpoint must not erase a prior good snapshot.
            previous_value = (self.data or {}).get("value")
            if isinstance(previous_value, dict):
                for key in ("classes", "inventory"):
                    current = value.get(key)
                    previous = previous_value.get(key)
                    if (
                        isinstance(current, dict)
                        and current.get("error")
                        and isinstance(previous, dict)
                        and isinstance(previous.get("items"), list)
                    ):
                        value[key] = {
                            **previous,
                            "error": current["error"],
                            "source_stale": True,
                        }
            value["source_stale"] = any(
                isinstance(value.get(key), dict)
                and value[key].get("source_stale") is True
                for key in ("classes", "inventory")
            )
        if self._name == "online":
            value["online_last_successful_update"] = attempted_at
            if value.get("source") == "blockfront_cloud_api":
                value["cloud_last_successful_update"] = attempted_at

        return {
            "value": value,
            "updated_at": attempted_at,
            "last_successful_update": attempted_at,
            "last_attempt": attempted_at,
            "stale": value.get("source_stale") is True,
            "last_error": None,
        }


@dataclass(slots=True)
class BlockFrontRuntimeData:
    """Runtime API client and update coordinators for a config entry."""

    api: BlockFrontApi
    coordinators: dict[str, BlockFrontCoordinator]


type BlockFrontConfigEntry = ConfigEntry[BlockFrontRuntimeData]


def create_runtime(hass: HomeAssistant, entry: ConfigEntry) -> BlockFrontRuntimeData:
    """Build an API client and independently scheduled data groups."""
    options = dict(entry.options)
    api_key = options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY)
    api_base_url = options.get(CONF_API_BASE_URL) or entry.data.get(CONF_API_BASE_URL)
    api = BlockFrontApi(async_get_clientsession(hass), api_key=api_key, api_base_url=api_base_url)

    async def fetch_profile() -> dict[str, Any]:
        return await api.async_get_player(entry.data["player_uuid"])

    async def fetch_matches() -> dict[str, Any]:
        return await api.async_get_match_data(entry.data["player_uuid"])

    async def fetch_status() -> dict[str, Any]:
        return parse_service_status(await api.async_get_status())

    async def fetch_analytics() -> dict[str, Any]:
        return await api.async_get_analytics(entry.data["player_uuid"])

    async def fetch_history() -> dict[str, Any]:
        profile_data = (
            (coordinators.get("profile").data or {}).get("value", {})
            if "profile" in coordinators
            else {}
        )
        return await api.async_get_player_history(
            entry.data["player_uuid"],
            clan_uuid=profile_data.get("clan_uuid") if isinstance(profile_data, dict) else None,
            clan_name=profile_data.get("clan") if isinstance(profile_data, dict) else None,
        )

    async def fetch_archive() -> dict[str, Any]:
        return await api.async_get_archive_data(entry.data["player_uuid"])

    async def fetch_global() -> dict[str, Any]:
        analytics_data = (
            (coordinators.get("analytics").data or {}).get("value", {})
            if "analytics" in coordinators
            else {}
        )
        featured_map = (
            analytics_data.get("most_played_map") if isinstance(analytics_data, dict) else None
        )
        return await api.async_get_global_data(
            featured_map=featured_map if isinstance(featured_map, str) and featured_map else None,
        )

    coordinators: dict[str, BlockFrontCoordinator] = {
        "analytics": BlockFrontCoordinator(
            hass,
            entry,
            "analytics",
            get_update_interval(options, "analytics"),
            fetch_analytics,
            {"value": None},
        ),
        "history": BlockFrontCoordinator(
            hass,
            entry,
            "history",
            get_update_interval(options, "history"),
            fetch_history,
            {"value": None},
        ),
        "archive": BlockFrontCoordinator(
            hass,
            entry,
            "archive",
            get_update_interval(options, "archive"),
            fetch_archive,
            {"value": None},
        ),
        "global": BlockFrontCoordinator(
            hass,
            entry,
            "global",
            get_update_interval(options, "global"),
            fetch_global,
            {"value": None},
        ),
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
