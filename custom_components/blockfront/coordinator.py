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
from .const import (
    CONF_API_BASE_URL,
    CONF_API_KEY,
    DOMAIN,
    MIN_INTERVALS,
    OPTION_ACTIVITY_COOLDOWN,
    OPTION_ACTIVITY_ENTITY,
    OPTION_ACTIVITY_MATCH,
    OPTION_ADAPTIVE_MARGIN,
    OPTION_ADAPTIVE_POLLING,
    OPTION_IDLE_HEARTBEAT,
    OPTION_PRESENCE_MODE,
    OPTION_PROFILE_SOURCE,
    OPTION_MATCHES_SOURCE,
    SOURCE_BLOCKLYTICS,
    SOURCE_VUIS,
    UPDATE_INTERVALS,
    get_update_interval,
)
from .vuis_api import VuisApi
from .polling import PollingPolicy
from .presence import Presence, PresenceTracker

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
        self.configured_interval = interval
        self.last_attempt_at: datetime | None = None
        self.last_successful_check_at: datetime | None = None
        self.polling_policy: PollingPolicy | None = None

    def set_interval(self, interval: timedelta | None) -> None:
        """Change cadence and replace an already scheduled timer."""
        self.update_interval = interval
        self._async_unsub_refresh()
        if interval is not None and self._listeners:
            self._schedule_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the group and keep a timestamped stale value on recoverable errors."""
        attempted_at = datetime.now(UTC).isoformat()
        self.last_attempt_at = datetime.now(UTC)
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

        old_value = self.data.get("value") if self.data else None
        value = _merge_last_good(old_value, value)
        if (
            self._name == "online"
            and isinstance(old_value, dict)
            and isinstance(value, dict)
            and value.get("source") == "statistics_api"
            and value.get("source_stale") is True
            and old_value.get("online_count") is not None
        ):
            old_stamp = old_value.get("source_timestamp")
            new_stamp = value.get("source_timestamp")
            if (
                not isinstance(new_stamp, str)
                or not isinstance(old_stamp, str)
                or _timestamp_is_newer(old_stamp, new_stamp)
            ):
                value["online_count"] = old_value.get("online_count")
                value["source"] = old_value.get("source")
                value["source_timestamp"] = old_stamp
                value["retained_previous_source"] = True
        if self._name == "analytics":
            value = _merge_analytics_fields(old_value, value)
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
        self.last_successful_check_at = datetime.now(UTC)
        if self.polling_policy is not None:
            learned = self.polling_policy.observe(value)
            if self.update_interval is not None and learned != self.update_interval:
                self.set_interval(learned)
        if self.data and _snapshot_signature(self.data.get("value")) == _snapshot_signature(value):
            # Keep identical sensor data byte-for-byte stable so HA Recorder
            # does not write large history attributes on every ETag recheck.
            self.async_update_listeners()
            return self.data
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
    presence: Presence = Presence.UNKNOWN
    presence_tracker: PresenceTracker | None = None
    presence_entity: str | None = None
    presence_match: str = ""
    active_intervals: dict[str, timedelta] | None = None
    idle_intervals: dict[str, timedelta] | None = None
    adaptive_polling: bool = True
    idle_heartbeat: timedelta = timedelta(hours=1)
    progression: dict[str, int | float | None] | None = None
    presence_mode: str = "auto"
    reconciliation_pending: bool = False
    reconciliation_marker: str | None = None
    postgame_refresh_due: bool = False


type BlockFrontConfigEntry = ConfigEntry[BlockFrontRuntimeData]


def create_runtime(hass: HomeAssistant, entry: ConfigEntry) -> BlockFrontRuntimeData:
    """Build an API client and independently scheduled data groups."""
    options = dict(entry.options)
    api_key = options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY)
    api_base_url = options.get(CONF_API_BASE_URL) or entry.data.get(CONF_API_BASE_URL)
    api = BlockFrontApi(async_get_clientsession(hass), api_key=api_key, api_base_url=api_base_url)
    vuis = VuisApi(api)

    async def fetch_profile() -> dict[str, Any]:
        if options.get(OPTION_PROFILE_SOURCE, SOURCE_BLOCKLYTICS) == SOURCE_VUIS:
            return await vuis.async_get_player(entry.data["player_uuid"])
        return await api.async_get_player(entry.data["player_uuid"])

    async def fetch_matches() -> dict[str, Any]:
        if options.get(OPTION_MATCHES_SOURCE, SOURCE_BLOCKLYTICS) == SOURCE_VUIS:
            return await vuis.async_get_match_data(entry.data["player_uuid"])
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
    if options.get(OPTION_ADAPTIVE_POLLING, True):
        margin = int(options.get(OPTION_ADAPTIVE_MARGIN, 10)) / 100
        for name, coordinator in coordinators.items():
            base = get_update_interval(options, name)
            coordinator.polling_policy = PollingPolicy(
                timedelta(seconds=MIN_INTERVALS[UPDATE_INTERVALS[name]]), base, margin
            )
    player_groups = ("analytics", "history", "archive", "profile", "matches")
    options = dict(entry.options)
    active_intervals = {
        name: timedelta(seconds=MIN_INTERVALS[UPDATE_INTERVALS[name]]) for name in player_groups
    }
    idle_intervals = {
        name: min(
            max(coordinators[name].update_interval, active_intervals[name] * 4),
            timedelta(days=1),
        )
        for name in player_groups
    }
    cooldown = max(0, int(options.get(OPTION_ACTIVITY_COOLDOWN, 30)))
    runtime = BlockFrontRuntimeData(
        api=api,
        coordinators=coordinators,
        presence_tracker=PresenceTracker(timedelta(minutes=cooldown)),
        presence_entity=options.get(OPTION_ACTIVITY_ENTITY) or None,
        presence_match=str(options.get(OPTION_ACTIVITY_MATCH, "BlockFront")),
        active_intervals=active_intervals,
        idle_intervals=idle_intervals,
        adaptive_polling=bool(options.get(OPTION_ADAPTIVE_POLLING, True)),
        idle_heartbeat=timedelta(
            minutes=max(15, min(360, int(options.get(OPTION_IDLE_HEARTBEAT, 60))))
        ),
        presence_mode=str(options.get(OPTION_PRESENCE_MODE, "auto")),
    )
    if runtime.presence_mode == "force_active":
        runtime.presence = Presence.ACTIVE
    elif runtime.presence_mode == "force_idle":
        runtime.presence = Presence.INACTIVE
    if runtime.adaptive_polling and runtime.presence_mode == "force_active":
        for name in player_groups:
            coordinators[name].set_interval(active_intervals[name])
    elif runtime.adaptive_polling and runtime.presence_mode == "force_idle":
        for name in player_groups:
            coordinators[name].set_interval(None)
    elif runtime.adaptive_polling and not runtime.presence_entity:
        for name in player_groups:
            coordinator = coordinators[name]
            heartbeat = max(idle_intervals[name], runtime.idle_heartbeat)
            coordinator.set_interval(heartbeat)
            if coordinator.polling_policy is not None:
                coordinator.polling_policy.minimum = heartbeat
                coordinator.polling_policy.maximum = heartbeat
    return runtime


def update_presence(runtime: BlockFrontRuntimeData, state: str) -> Presence:
    """Apply a selected HA activity sensor and reschedule player datasets."""
    if runtime.presence_tracker is None:
        return Presence.UNKNOWN
    previous = runtime.presence
    was_reconciliation_pending = runtime.reconciliation_pending
    profile_value = (runtime.coordinators["profile"].data or {}).get("value", {})
    matches_value = (runtime.coordinators["matches"].data or {}).get("value", {})
    profile_marker = (
        profile_value.get("source_timestamp") if isinstance(profile_value, dict) else None
    )
    matches_marker = (
        matches_value.get("source_timestamp") if isinstance(matches_value, dict) else None
    )
    current_marker = f"{profile_marker or ''}|{matches_marker or ''}"
    runtime.presence = (
        Presence.ACTIVE
        if runtime.presence_mode == "force_active"
        else Presence.INACTIVE
        if runtime.presence_mode == "force_idle"
        else runtime.presence_tracker.update(state, match=runtime.presence_match)
    )
    if runtime.presence_mode != "auto":
        runtime.reconciliation_pending = False
    elif previous is Presence.ACTIVE and runtime.presence is Presence.COOLDOWN:
        runtime.reconciliation_pending = True
        runtime.reconciliation_marker = current_marker
        runtime.postgame_refresh_due = True
    elif runtime.reconciliation_pending and current_marker != runtime.reconciliation_marker:
        runtime.reconciliation_pending = False
    if runtime.adaptive_polling and (
        runtime.presence is not previous
        or was_reconciliation_pending != runtime.reconciliation_pending
    ):
        for name, interval in (runtime.active_intervals or {}).items():
            coordinator = runtime.coordinators[name]
            if runtime.presence in (Presence.ACTIVE, Presence.COOLDOWN):
                next_interval: timedelta | None = interval
            elif runtime.presence is Presence.INACTIVE and runtime.reconciliation_pending:
                next_interval = runtime.idle_heartbeat
            elif runtime.presence is Presence.INACTIVE and (
                runtime.presence_mode == "force_idle"
                or (runtime.presence_entity or "").startswith("binary_sensor.")
            ):
                next_interval = None
            else:
                next_interval = max(
                    (runtime.idle_intervals or {}).get(name, interval), runtime.idle_heartbeat
                )
            if coordinator.polling_policy is not None and next_interval is not None:
                coordinator.polling_policy.minimum = next_interval
                coordinator.polling_policy.maximum = (
                    max(next_interval, coordinator.configured_interval)
                    if runtime.presence in (Presence.ACTIVE, Presence.COOLDOWN)
                    else next_interval
                )
            coordinator.set_interval(next_interval)
    if runtime.presence is not previous:
        for coordinator in runtime.coordinators.values():
            coordinator.async_update_listeners()
    return runtime.presence


def _merge_last_good(previous: Any, current: Any) -> Any:
    """Retain prior usable nested dataset values when a sibling fetch fails."""
    if isinstance(previous, dict) and isinstance(current, dict):
        merged = dict(current)
        for key, value in current.items():
            old = previous.get(key)
            if isinstance(value, dict) and isinstance(old, dict):
                has_error = value.get("error") is not None
                value_fields = ("data", "points", "items")
                if has_error and any(old.get(field) is not None for field in value_fields):
                    kept = dict(old)
                    kept.update(
                        {
                            name: item
                            for name, item in value.items()
                            if name in {"error", "source_stale", "last_attempt"}
                        }
                    )
                    kept["last_successful_update"] = old.get("last_successful_update")
                    merged[key] = kept
                else:
                    merged[key] = _merge_last_good(old, value)
        return merged
    return current


def _snapshot_signature(value: Any) -> Any:
    """Strip transport heartbeat fields before comparing source snapshots."""
    ignored = {"last_attempt", "last_successful_update", "_polling", "http_checked_at"}
    if isinstance(value, dict):
        return tuple(
            (key, _snapshot_signature(item))
            for key, item in sorted(value.items())
            if key not in ignored
        )
    if isinstance(value, list):
        return tuple(_snapshot_signature(item) for item in value)
    return value


def _timestamp_is_newer(left: str, right: str) -> bool:
    """Compare ISO source timestamps without making fetch-time assumptions."""
    try:
        left_at = datetime.fromisoformat(left.replace("Z", "+00:00"))
        right_at = datetime.fromisoformat(right.replace("Z", "+00:00"))
    except ValueError:
        return False
    if left_at.tzinfo is None or right_at.tzinfo is None:
        return False
    return left_at > right_at


def _merge_analytics_fields(previous: Any, current: dict[str, Any]) -> dict[str, Any]:
    """Keep public analytics fields from only the failed endpoint family."""
    if not isinstance(previous, dict):
        return current
    groups = {
        "summary_error": ("tracked_matches", "computed_at", "source_timestamp"),
        "maps_error": ("maps", "most_played_map", "most_played_map_key"),
        "modes_error": (
            "modes",
            "sample_matches",
            "recorded_wins",
            "recorded_losses",
            "recorded_win_rate",
            "average_match_score",
        ),
    }
    for error_key, fields in groups.items():
        if current.get(error_key):
            for key in fields:
                current[key] = previous.get(key)
    return current
