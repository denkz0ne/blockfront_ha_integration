"""Sensors for BlockFront player statistics and service status."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from types import SimpleNamespace
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PLAYER_UUID, CONF_USERNAME, DOMAIN
from .coordinator import BlockFrontConfigEntry, BlockFrontCoordinator
from .presence import Presence

PARALLEL_UPDATES = 0

RANK_EXP_THRESHOLDS = (
    0,
    1,
    1001,
    3001,
    6001,
    10001,
    16001,
    23501,
    32501,
    43001,
    55001,
    69001,
    85001,
    103001,
    123001,
    145001,
    169001,
    195001,
    223001,
    253001,
)
CLASS_NAMES = {
    "0": "Rifleman",
    "1": "Lt. Rifle",
    "2": "Assault",
    "3": "Support",
    "4": "Medic",
    "5": "Sniper",
    "6": "Gunner",
    "7": "Anti-Tank",
    "8": "Specialist",
    "9": "Commander",
}
ICON_BASE_PATH = "/api/blockfront/icons"
_PLAYER_DATA_COORDINATORS = frozenset({"profile", "matches", "archive", "history", "analytics"})


class _PlayerNamedEntity:
    """Prefix player-specific friendly names without changing their entity IDs."""

    _attr_player_specific_name = False
    _username: str

    def _friendly_name_internal(self) -> str | None:
        """Return a bracketed player name for entities tied to one player's UUID."""
        if self._attr_player_specific_name:
            name = self.name
            if isinstance(name, str):
                return f"[{self._username}] {name}"
        return super()._friendly_name_internal()


@dataclass(frozen=True, kw_only=True)
class BlockFrontSensorDescription(SensorEntityDescription):
    """Add a coordinator and value key to a Home Assistant sensor description."""

    coordinator_key: str
    value_key: str | None = None


SENSOR_DESCRIPTIONS = (
    BlockFrontSensorDescription(
        key="kills",
        translation_key="kills",
        coordinator_key="profile",
        value_key="kills",
        icon="mdi:target",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="deaths",
        translation_key="deaths",
        coordinator_key="profile",
        value_key="deaths",
        icon="mdi:skull",
        native_unit_of_measurement="deaths",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="kd_ratio",
        translation_key="kd_ratio",
        coordinator_key="profile",
        value_key="kd",
        icon="mdi:scale-balance",
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="head_shots",
        translation_key="head_shots",
        coordinator_key="profile",
        value_key="head_shots",
        icon="mdi:crosshairs",
        native_unit_of_measurement="headshots",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="first_bloods",
        translation_key="first_bloods",
        coordinator_key="profile",
        value_key="first_bloods",
        icon="mdi:water",
        native_unit_of_measurement="first bloods",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="no_scopes",
        translation_key="no_scopes",
        coordinator_key="profile",
        value_key="no_scopes",
        icon="mdi:scope",
        native_unit_of_measurement="no-scopes",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="total_games",
        translation_key="total_games",
        coordinator_key="profile",
        value_key="total_games",
        icon="mdi:gamepad-variant",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="time_played",
        translation_key="time_played",
        coordinator_key="profile",
        value_key="time_played",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="rank",
        translation_key="rank",
        coordinator_key="profile",
        value_key="rank",
        icon="mdi:medal",
    ),
    BlockFrontSensorDescription(
        key="prestige",
        translation_key="prestige",
        coordinator_key="profile",
        value_key="prestige",
        icon="mdi:star-circle",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="assists",
        translation_key="assists",
        coordinator_key="profile",
        value_key="assists",
        icon="mdi:handshake",
        native_unit_of_measurement="assists",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="back_stabs",
        translation_key="back_stabs",
        coordinator_key="profile",
        value_key="back_stabs",
        icon="mdi:knife",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="bot_kills",
        translation_key="bot_kills",
        coordinator_key="profile",
        value_key="bot_kills",
        icon="mdi:robot",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="captures",
        translation_key="captures",
        coordinator_key="profile",
        value_key="captures",
        icon="mdi:flag-checkered",
        native_unit_of_measurement="captures",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="exp",
        translation_key="exp",
        coordinator_key="profile",
        value_key="exp",
        icon="mdi:star-four-points",
        native_unit_of_measurement="XP",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="class_exp",
        translation_key="class_exp",
        coordinator_key="archive",
        value_key="class_exp",
        icon="mdi:account-star",
        native_unit_of_measurement="XP",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="fire_kills",
        translation_key="fire_kills",
        coordinator_key="profile",
        value_key="fire_kills",
        icon="mdi:fire",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="heal_assists",
        translation_key="heal_assists",
        coordinator_key="profile",
        value_key="heal_assists",
        icon="mdi:medical-bag",
        native_unit_of_measurement="assists",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="highest_death_streak",
        translation_key="highest_death_streak",
        coordinator_key="profile",
        value_key="highest_death_streak",
        icon="mdi:skull-crossbones",
        native_unit_of_measurement="deaths",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="highest_kill_streak",
        translation_key="highest_kill_streak",
        coordinator_key="profile",
        value_key="highest_kill_streak",
        icon="mdi:fire-circle",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="hs_kr",
        translation_key="hs_kr",
        coordinator_key="profile",
        value_key="hs_kr",
        icon="mdi:crosshairs-gps",
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="infected_kills",
        translation_key="infected_kills",
        coordinator_key="profile",
        value_key="infected_kills",
        icon="mdi:zombie",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="infected_matches_won",
        translation_key="infected_matches_won",
        coordinator_key="profile",
        value_key="infected_matches_won",
        icon="mdi:trophy",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="infected_rounds_won",
        translation_key="infected_rounds_won",
        coordinator_key="profile",
        value_key="infected_rounds_won",
        icon="mdi:check-decagram",
        native_unit_of_measurement="rounds",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="match_karma",
        translation_key="match_karma",
        coordinator_key="profile",
        value_key="match_karma",
        icon="mdi:heart",
        native_unit_of_measurement="karma",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="objective_score",
        translation_key="objective_score",
        coordinator_key="profile",
        value_key="objective_score",
        icon="mdi:flag",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="trophies",
        translation_key="trophies",
        coordinator_key="profile",
        value_key="trophies",
        icon="mdi:trophy-variant",
        native_unit_of_measurement="trophies",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="vehicle_kills",
        translation_key="vehicle_kills",
        coordinator_key="profile",
        value_key="vehicle_kills",
        icon="mdi:car",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="skill_rank",
        translation_key="skill_rank",
        coordinator_key="profile",
        value_key="skill_rank",
        icon="mdi:medal-outline",
    ),
    BlockFrontSensorDescription(
        key="clan",
        translation_key="clan",
        coordinator_key="profile",
        value_key="clan",
        icon="mdi:account-group",
    ),
    BlockFrontSensorDescription(
        key="latest_match",
        translation_key="latest_match",
        coordinator_key="matches",
        icon="mdi:clipboard-text-clock",
    ),
    BlockFrontSensorDescription(
        key="latest_match_score",
        translation_key="latest_match_score",
        coordinator_key="matches",
        value_key="score",
        icon="mdi:counter",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="online_players",
        translation_key="online_players",
        coordinator_key="online",
        value_key="online_count",
        icon="mdi:account-group",
        native_unit_of_measurement="players",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_polling_status",
        translation_key="cloud_polling_status",
        coordinator_key="online",
        value_key="polling_status",
        icon="mdi:cloud-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BlockFrontSensorDescription(
        key="service_status",
        translation_key="service_status",
        coordinator_key="status",
        value_key="status",
        icon="mdi:server-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

# Analytics describe the recorded sample, never the player's full career.
SENSOR_DESCRIPTIONS += (
    BlockFrontSensorDescription(
        key="tracked_matches",
        translation_key="tracked_matches",
        coordinator_key="analytics",
        value_key="tracked_matches",
        icon="mdi:clipboard-list",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="recorded_wins",
        translation_key="recorded_wins",
        coordinator_key="analytics",
        value_key="recorded_wins",
        icon="mdi:trophy",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="recorded_losses",
        translation_key="recorded_losses",
        coordinator_key="analytics",
        value_key="recorded_losses",
        icon="mdi:shield-off",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="recorded_win_rate",
        translation_key="recorded_win_rate",
        coordinator_key="analytics",
        value_key="recorded_win_rate",
        icon="mdi:trophy-outline",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="average_match_score",
        translation_key="average_match_score",
        coordinator_key="analytics",
        value_key="average_match_score",
        icon="mdi:counter",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="most_played_map",
        translation_key="most_played_map",
        coordinator_key="analytics",
        value_key="most_played_map",
        icon="mdi:map",
    ),
    BlockFrontSensorDescription(
        key="latest_match_duration",
        translation_key="latest_match_duration",
        coordinator_key="matches",
        value_key="duration_seconds",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="latest_match_end",
        translation_key="latest_match_end",
        coordinator_key="matches",
        value_key="ended_at",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    BlockFrontSensorDescription(
        key="api_polling_status",
        translation_key="api_polling_status",
        coordinator_key="status",
        value_key="api_polling_status",
        icon="mdi:api",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BlockFrontSensorDescription(
        key="api_requests_remaining",
        translation_key="api_requests_remaining",
        coordinator_key="status",
        value_key="api_rate_limit_remaining",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="requests",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="inventory_items",
        translation_key="inventory_items",
        coordinator_key="archive",
        icon="mdi:treasure-chest",
        native_unit_of_measurement="items",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="profile_history",
        translation_key="profile_history",
        coordinator_key="history",
        icon="mdi:chart-timeline-variant",
        native_unit_of_measurement="snapshots",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="competitive_rank_history",
        translation_key="competitive_rank_history",
        coordinator_key="history",
        icon="mdi:medal-outline",
    ),
    BlockFrontSensorDescription(
        key="season_score",
        translation_key="season_score",
        coordinator_key="history",
        icon="mdi:trophy",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="map_statistics",
        translation_key="map_statistics",
        coordinator_key="global",
        icon="mdi:map-legend",
        native_unit_of_measurement="maps",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="population_history",
        translation_key="population_history",
        coordinator_key="global",
        icon="mdi:chart-areaspline",
        native_unit_of_measurement="readings",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="recorded_game_trends",
        translation_key="recorded_game_trends",
        coordinator_key="global",
        icon="mdi:chart-bar",
        native_unit_of_measurement="days",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="player_leaderboard",
        translation_key="player_leaderboard",
        coordinator_key="global",
        icon="mdi:podium",
        native_unit_of_measurement="players",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="clan_leaderboard",
        translation_key="clan_leaderboard",
        coordinator_key="global",
        icon="mdi:account-group",
        native_unit_of_measurement="clans",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="competitive_leaderboard",
        translation_key="competitive_leaderboard",
        coordinator_key="global",
        icon="mdi:medal",
        native_unit_of_measurement="players",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="featured_map",
        translation_key="featured_map",
        coordinator_key="global",
        icon="mdi:map-marker-star",
    ),
)

_MATCH_ATTRIBUTE_KEYS = (
    "ended_at",
    "started_at_estimated",
    "environment",
    "map",
    "game",
    "kills",
    "deaths",
    "assists",
    "score",
    "player_team",
    "winner_team",
    "duration_seconds",
    "placement",
    "match_id",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BlockFrontConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensors for a configured player."""
    async_add_entities(
        [
            BlockFrontSensor(
                entry.runtime_data.coordinators[description.coordinator_key],
                entry,
                description,
            )
            for description in SENSOR_DESCRIPTIONS
        ]
        + [
            BlockFrontProgressSensor(entry, key)
            for key in ("exp", "kills", "deaths", "total_games", "time_played", "head_shots")
        ]
    )


class BlockFrontSensor(_PlayerNamedEntity, CoordinatorEntity[BlockFrontCoordinator], SensorEntity):
    """Represent a single player statistic or service value."""

    entity_description: BlockFrontSensorDescription

    def __init__(
        self,
        coordinator: BlockFrontCoordinator,
        entry: ConfigEntry,
        description: BlockFrontSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        player_uuid = entry.data[CONF_PLAYER_UUID]
        self._player_uuid = player_uuid
        self._username = entry.data[CONF_USERNAME]
        runtime = getattr(entry, "runtime_data", None)
        self._runtime = runtime or SimpleNamespace(
            presence=Presence.UNKNOWN,
            presence_entity=None,
            presence_mode="auto",
            presence_tracker=None,
            reconciliation_pending=False,
            coordinators={"profile": coordinator, "global": coordinator},
            progression=None,
        )
        self._api = getattr(runtime, "api", None) if description.key.startswith("api_") else None
        self._polling_coordinators = runtime.coordinators if self._api is not None else {}
        self._attr_unique_id = f"{player_uuid}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_player_specific_name = description.coordinator_key in _PLAYER_DATA_COORDINATORS
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, player_uuid)},
            name=self._username,
            manufacturer="BlockFront",
            model="Player statistics",
        )

    async def async_added_to_hass(self) -> None:
        """Refresh quota diagnostics after every data group, without extra requests."""
        await super().async_added_to_hass()
        for coordinator in self._polling_coordinators.values():
            if coordinator is not self.coordinator:
                self.async_on_remove(coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def entity_picture(self) -> str | None:
        """Return a locally served BlockFront rank badge for rank sensors."""
        if self.entity_description.coordinator_key != "profile":
            return None

        profile = (self.coordinator.data or {}).get("value")
        if not isinstance(profile, dict):
            return None

        if self.entity_description.key == "skill_rank":
            skill_rank = profile.get("skill_rank")
            index = skill_rank.get("index") if isinstance(skill_rank, dict) else None
            if isinstance(index, int) and not isinstance(index, bool) and 0 <= index <= 16:
                return f"{ICON_BASE_PATH}/skill_ranks/{index}.png"
            return f"{ICON_BASE_PATH}/skill_ranks/none.png"

        if self.entity_description.key == "rank":
            index = _rank_image_index(profile.get("exp"))
            if index is not None:
                return f"{ICON_BASE_PATH}/ranks/{index}.png"
        return None

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return a validated state value without inventing missing values."""
        if self._api is not None:
            return self._api.polling_data().get(self.entity_description.value_key)
        data = self.coordinator.data or {}
        value = data.get("value")
        if not isinstance(value, dict):
            return None

        if self.entity_description.coordinator_key == "archive":
            if self.entity_description.key == "class_exp":
                classes = value.get("classes")
                return _class_exp_total(classes.get("items") if isinstance(classes, dict) else None)
            if self.entity_description.key == "inventory_items":
                inventory = value.get("inventory")
                items = inventory.get("items") if isinstance(inventory, dict) else None
                return len(items) if isinstance(items, list) else None

        if self.entity_description.coordinator_key == "history":
            if self.entity_description.key == "profile_history":
                points = _history_points(value, "lifetime")
                return len(points) if points is not None else None
            if self.entity_description.key == "competitive_rank_history":
                points = _history_points(value, "competitive")
                latest = points[-1] if points else None
                rank = latest.get("rank") if isinstance(latest, dict) else None
                return rank.get("title") if isinstance(rank, dict) else None
            if self.entity_description.key == "season_score":
                points = _history_points(value, "season")
                latest = points[-1] if points else None
                score = latest.get("score") if isinstance(latest, dict) else None
                return (
                    score
                    if isinstance(score, (int, float)) and not isinstance(score, bool)
                    else None
                )

        if self.entity_description.coordinator_key == "global":
            datasets = value.get("datasets")
            if not isinstance(datasets, dict):
                return None
            key = self.entity_description.key
            dataset_key = {
                "map_statistics": "maps",
                "population_history": "online_history",
                "recorded_game_trends": "trends",
                "player_leaderboard": "players",
                "clan_leaderboard": "clans",
                "competitive_leaderboard": "competitive",
            }.get(key)
            if key == "featured_map":
                featured = value.get("featured_map")
                details = featured.get("data") if isinstance(featured, dict) else None
                return details.get("map") if isinstance(details, dict) else None
            dataset = datasets.get(dataset_key) if dataset_key else None
            rows = dataset.get("data") if isinstance(dataset, dict) else None
            if key == "map_statistics":
                return len(rows) if isinstance(rows, list) else None
            if key == "population_history":
                points = rows.get("points") if isinstance(rows, dict) else None
                return len(points) if isinstance(points, list) else None
            if key == "recorded_game_trends":
                daily = rows.get("daily") if isinstance(rows, dict) else None
                return len(daily) if isinstance(daily, list) else None
            if isinstance(rows, list):
                return len(rows)
            return None

        if self.entity_description.coordinator_key == "matches":
            matches = value.get("matches")
            if not isinstance(matches, list) or not matches:
                return None
            match = matches[0]
            if not isinstance(match, dict):
                return None
            if self.entity_description.key == "latest_match":
                result = match.get("result")
                return result if isinstance(result, str) and result else None
            result = match.get(self.entity_description.value_key)
            if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
                if isinstance(result, str):
                    try:
                        timestamp = datetime.fromisoformat(result.replace("Z", "+00:00"))
                        return timestamp if timestamp.tzinfo is not None else None
                    except ValueError:
                        pass
                return None
            if isinstance(result, (int, float)) and not isinstance(result, bool):
                return result if isfinite(result) else None
            return None

        if self.entity_description.value_key is None:
            return None
        if self.entity_description.coordinator_key == "profile":
            value = value.get(self.entity_description.value_key)
        else:
            value = value.get(self.entity_description.value_key)

        if self.entity_description.value_key == "class_exp":
            return _class_exp_total(value)
        if self.entity_description.value_key == "skill_rank":
            return value.get("title") if isinstance(value, dict) else None
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return None
        if isinstance(value, str) and not value:
            return None
        if self.entity_description.key in {"kd_ratio", "hs_kr"}:
            return round(value, 2) if isinstance(value, (int, float)) and isfinite(value) else None
        if isinstance(value, float) and not isfinite(value):
            return None
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose match detail, source, and update health as state attributes."""
        coordinator_data = self.coordinator.data or {}
        attributes: dict[str, Any] = {
            "last_successful_update": coordinator_data.get("last_successful_update"),
            "last_attempt": coordinator_data.get("last_attempt"),
            "last_successful_http_check": coordinator_data.get("last_successful_update"),
            "stale": coordinator_data.get("stale", True),
            "last_error": coordinator_data.get("last_error"),
            "playing_state": self._runtime.presence.value,
            "presence_source": self._runtime.presence_entity
            or ("manual_override" if self._runtime.presence_mode != "auto" else None),
            "presence_mode": self._runtime.presence_mode,
            "presence_confidence": (
                "manual_override"
                if self._runtime.presence_mode != "auto"
                else "configured_binary_signal"
                if self._runtime.presence_entity
                and self._runtime.presence_entity.startswith("binary_sensor.")
                else "probable_active_window"
                if self._runtime.presence_entity
                else "unknown_no_presence_signal"
            ),
            "last_activity_observed": (
                self._runtime.presence_tracker.last_active.isoformat()
                if self._runtime.presence_tracker and self._runtime.presence_tracker.last_active
                else None
            ),
            "personal_collection": "reconciling"
            if self._runtime.reconciliation_pending
            else "paused"
            if self._runtime.presence.value == "inactive"
            and self.coordinator.update_interval is None
            else "running",
            "next_personal_check": (
                (
                    datetime.fromisoformat(coordinator_data["last_attempt"])
                    + self.coordinator.update_interval
                ).isoformat()
                if self.entity_description.coordinator_key
                in {"profile", "matches", "analytics", "history", "archive"}
                and isinstance(coordinator_data.get("last_attempt"), str)
                and self.coordinator.update_interval is not None
                else None
            ),
        }
        if self._api is not None:
            polling = self._api.polling_data()
            profile_coordinator = self._runtime.coordinators["profile"]
            profile_data = (profile_coordinator.data or {}).get("value", {})
            attributes["personal_source_timestamp"] = (
                profile_data.get("source_timestamp") if isinstance(profile_data, dict) else None
            )
            attributes["personal_last_http_check"] = (
                getattr(profile_coordinator, "last_successful_check_at", None).isoformat()
                if getattr(profile_coordinator, "last_successful_check_at", None)
                else None
            )
            attributes["next_personal_check"] = (
                (
                    profile_coordinator.last_attempt_at + profile_coordinator.update_interval
                ).isoformat()
                if getattr(profile_coordinator, "last_attempt_at", None)
                and profile_coordinator.update_interval
                else None
            )
            attributes["personal_collection"] = (
                "reconciling"
                if self._runtime.reconciliation_pending
                else "paused"
                if profile_coordinator.update_interval is None
                else "running"
            )
            global_coordinator = self._runtime.coordinators["global"]
            global_data = (global_coordinator.data or {}).get("value", {})
            global_datasets = (
                global_data.get("datasets", {}) if isinstance(global_data, dict) else {}
            )
            timestamps = (
                [
                    item.get("source_timestamp")
                    for item in global_datasets.values()
                    if isinstance(item, dict) and isinstance(item.get("source_timestamp"), str)
                ]
                if isinstance(global_datasets, dict)
                else []
            )
            attributes["global_source_timestamp"] = max(timestamps, default=None)
            attributes["global_last_http_check"] = (
                getattr(global_coordinator, "last_successful_check_at", None).isoformat()
                if getattr(global_coordinator, "last_successful_check_at", None)
                else None
            )
            attributes["next_global_check"] = (
                (
                    global_coordinator.last_attempt_at + global_coordinator.update_interval
                ).isoformat()
                if getattr(global_coordinator, "last_attempt_at", None)
                and global_coordinator.update_interval
                else None
            )
            attributes.update(
                {
                    "last_successful_update": polling.get("api_last_successful_update"),
                    "last_attempt": polling.get("api_last_attempt"),
                    "last_successful_http_check": polling.get("api_last_successful_update"),
                    "last_error": polling.get("api_last_error"),
                    "stale": polling.get("api_polling_status") != "available",
                }
            )
        value = coordinator_data.get("value")
        if not isinstance(value, dict):
            return attributes

        attributes.update(
            {
                "source": value.get("source"),
                "source_timestamp": value.get("source_timestamp"),
                "source_stale": value.get("source_stale"),
            }
        )
        key = self.entity_description.coordinator_key
        if key == "profile":
            attributes["unavailable_fields"] = value.get("unavailable_fields")
            if self.entity_description.key == "match_karma":
                attributes["supplement_source"] = value.get("supplement_source")
                attributes["supplement_error"] = value.get("supplement_error")
                attributes["source"] = value.get("supplement_source")
                attributes["stale"] = attributes["stale"] or bool(value.get("supplement_error"))
                attributes["last_error"] = value.get("supplement_error") or attributes["last_error"]
            if self.entity_description.value_key == "skill_rank":
                skill_rank = value.get("skill_rank")
                if isinstance(skill_rank, dict):
                    attributes.update(
                        {
                            "skill_rank_index": skill_rank.get("index"),
                            "skill_rank_color": skill_rank.get("color"),
                            "rating_band": skill_rank.get("ratingBand"),
                        }
                    )
        elif key == "archive":
            classes = value.get("classes")
            inventory = value.get("inventory")
            if self.entity_description.key == "class_exp" and isinstance(classes, dict):
                attributes.update(
                    {
                        "class_exp": _named_class_exp(classes.get("items")),
                        "captured_at": _epoch_millis_to_iso(classes.get("captured_at")),
                        "archive_source": classes.get("source"),
                        "archive_source_timestamp": classes.get("source_timestamp"),
                        "archive_source_stale": classes.get("source_stale"),
                        "archive_error": classes.get("error"),
                    }
                )
            elif self.entity_description.key == "inventory_items" and isinstance(inventory, dict):
                attributes.update(
                    {
                        "items": inventory.get("items"),
                        "captured_at": _epoch_millis_to_iso(inventory.get("captured_at")),
                        "archive_source": inventory.get("source"),
                        "archive_source_timestamp": inventory.get("source_timestamp"),
                        "archive_source_stale": inventory.get("source_stale"),
                        "archive_error": inventory.get("error"),
                    }
                )
        elif key == "history":
            lifetime = value.get("lifetime")
            competitive = value.get("competitive")
            season = value.get("season")
            if self.entity_description.key == "profile_history" and isinstance(lifetime, dict):
                attributes.update(
                    {
                        "history_points": lifetime.get("points"),
                        "history_source_timestamp": lifetime.get("source_timestamp"),
                        "history_source_stale": lifetime.get("source_stale"),
                        "history_error": lifetime.get("error"),
                    }
                )
            elif self.entity_description.key == "competitive_rank_history" and isinstance(
                competitive, dict
            ):
                points = competitive.get("points")
                latest = points[-1] if isinstance(points, list) and points else None
                rank = latest.get("rank") if isinstance(latest, dict) else None
                estimate = latest.get("estimate") if isinstance(latest, dict) else None
                attributes.update(
                    {
                        "rank_index": rank.get("index") if isinstance(rank, dict) else None,
                        "rank_color": rank.get("color") if isinstance(rank, dict) else None,
                        "approximate_rating": estimate.get("approx")
                        if isinstance(estimate, dict)
                        else None,
                        "rank_history": points,
                        "source_timestamp": competitive.get("source_timestamp"),
                        "source_stale": competitive.get("source_stale"),
                        "history_error": competitive.get("error"),
                    }
                )
            elif self.entity_description.key == "season_score" and isinstance(season, dict):
                attributes.update(
                    {
                        "score_history": season.get("points"),
                        "source_timestamp": season.get("source_timestamp"),
                        "source_stale": season.get("source_stale"),
                        "history_error": season.get("error"),
                    }
                )
            clan = value.get("clan")
            if isinstance(clan, dict):
                attributes["clan_data"] = clan
        elif key == "global":
            datasets = value.get("datasets")
            if isinstance(datasets, dict):
                target = {
                    "map_statistics": "maps",
                    "population_history": "online_history",
                    "recorded_game_trends": "trends",
                    "player_leaderboard": "players",
                    "clan_leaderboard": "clans",
                    "competitive_leaderboard": "competitive",
                }.get(self.entity_description.key)
                dataset = datasets.get(target) if target else None
                rows = dataset.get("data") if isinstance(dataset, dict) else None
                if self.entity_description.key == "map_statistics" and isinstance(rows, list):
                    attributes["maps"] = rows
                elif self.entity_description.key == "population_history" and isinstance(rows, dict):
                    attributes.update(
                        {
                            "points": rows.get("points"),
                            "hours": rows.get("hours"),
                            "bucket_seconds": rows.get("bucketSeconds"),
                        }
                    )
                elif self.entity_description.key == "recorded_game_trends" and isinstance(
                    rows, dict
                ):
                    attributes.update({"daily": rows.get("daily"), "days": rows.get("days")})
                elif isinstance(rows, list):
                    attributes["top_10"] = rows[:10]
                    if self.entity_description.key == "player_leaderboard":
                        own = next(
                            (row for row in rows if row.get("uuid") == self._player_uuid), None
                        )
                        attributes["player_entry"] = own
                    elif self.entity_description.key == "competitive_leaderboard":
                        own = next(
                            (row for row in rows if row.get("uuid") == self._player_uuid), None
                        )
                        attributes["player_entry"] = own
                if isinstance(dataset, dict):
                    attributes["source_timestamp"] = dataset.get("source_timestamp")
                    attributes["source_stale"] = dataset.get("source_stale")
                    attributes["pagination"] = dataset.get("pagination")
            if self.entity_description.key == "featured_map":
                featured = value.get("featured_map")
                if isinstance(featured, dict):
                    attributes.update(
                        {
                            "map_details": featured.get("data"),
                            "source_timestamp": featured.get("source_timestamp"),
                            "source_stale": featured.get("source_stale"),
                            "map_error": featured.get("error"),
                        }
                    )
        elif key == "matches":
            matches = value.get("matches")
            match = matches[0] if isinstance(matches, list) and matches else None
            if isinstance(match, dict):
                attributes.update(
                    {key: match[key] for key in _MATCH_ATTRIBUTE_KEYS if key in match}
                )
                attributes["recent_matches_available"] = len(matches)
                attributes["pagination"] = value.get("pagination")
        elif key == "online":
            rate_limit = value.get("rate_limit")
            if not isinstance(rate_limit, dict):
                rate_limit = {}
            attributes.update(
                {
                    "source": value.get("source"),
                    "online_source": value.get("source"),
                    "source_timestamp": value.get("source_timestamp"),
                    "online_source_captured_at": value.get("source_timestamp"),
                    "online_is_stale": value.get("source_stale"),
                    "online_polling_status": value.get("polling_status"),
                    "api_error": value.get("api_error"),
                    "public_api_error": value.get("public_api_error"),
                    "source_freshness": value.get("source_freshness"),
                    "fallback_errors": value.get("fallback_errors"),
                    "source_errors": value.get("source_errors"),
                    "cloud_polling_status": value.get("polling_status"),
                    "cloud_stale": value.get("source_stale", True),
                    "cloud_last_successful_update": value.get("cloud_last_successful_update"),
                    "cloud_retry_after": value.get("retry_after"),
                    "cloud_rate_limit_limit": _rate_limit_value(
                        rate_limit, "RateLimit-Limit", "X-RateLimit-Limit"
                    ),
                    "cloud_rate_limit_remaining": _rate_limit_value(
                        rate_limit, "RateLimit-Remaining", "X-RateLimit-Remaining"
                    ),
                    "cloud_rate_limit_reset": _rate_limit_value(
                        rate_limit, "RateLimit-Reset", "X-RateLimit-Reset"
                    ),
                    "cloud_rate_limit_headers": rate_limit,
                }
            )
            if self.entity_description.key == "cloud_polling_status":
                attributes["poll_interval_seconds"] = int(
                    self.coordinator.update_interval.total_seconds()
                )
        elif key == "analytics":
            attributes.update(
                {
                    "sample_matches": value.get("sample_matches"),
                    "computed_at": value.get("computed_at"),
                    "scope": "recorded_matches_only",
                }
            )
            if self.entity_description.key == "most_played_map":
                attributes["maps"] = _round_rows(value.get("maps"))
                attributes["modes"] = _round_rows(value.get("modes"))
                attributes["datasets"] = value.get("datasets")
        elif key == "status":
            polling = self._api.polling_data() if self._api is not None else value
            attributes.update({k: v for k, v in polling.items() if k.startswith("api_")})
            attributes["datasets"] = value.get("datasets")
            attributes["stale_datasets"] = value.get("stale_datasets")
            attributes["player_data_available"] = value.get("player_data_available")
            attributes["server_version"] = value.get("server_version")
            attributes.update(
                {
                    "stale_feed_count": value.get("stale_feed_count"),
                    "api_version": value.get("version"),
                    "service_uptime_seconds": value.get("uptime_seconds"),
                    "upstream_error": value.get("upstream_error"),
                }
            )
        return _bound_attributes(attributes)


class BlockFrontProgressSensor(_PlayerNamedEntity, SensorEntity):
    """Expose a cumulative counter delta between distinct source snapshots."""

    _attr_has_entity_name = True

    def __init__(self, entry: BlockFrontConfigEntry, counter: str) -> None:
        self._entry = entry
        self._counter = counter
        self._username = entry.data[CONF_USERNAME]
        self._attr_player_specific_name = True
        self._attr_unique_id = f"{entry.data[CONF_PLAYER_UUID]}_{counter}_since_observation"
        self._attr_translation_key = f"{counter}_since_observation"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_PLAYER_UUID])},
            name=entry.data[CONF_USERNAME],
            manufacturer="BlockFront",
            model="Player statistics",
        )

    async def async_added_to_hass(self) -> None:
        """Update delta sensors with profile snapshot changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._entry.runtime_data.coordinators["profile"].async_add_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> int | float | None:
        """Return the last distinct source snapshot delta, when known."""
        return (self._entry.runtime_data.progression or {}).get(self._counter)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Label deltas with their actual observation interval."""
        value = (self._entry.runtime_data.coordinators["profile"].data or {}).get("value", {})
        return {
            "delta_window": "since_last_distinct_source_observation",
            "source_timestamp": value.get("source_timestamp") if isinstance(value, dict) else None,
            "source_stale": value.get("source_stale") if isinstance(value, dict) else None,
        }


def _class_exp_by_id(value: object) -> dict[str, int]:
    """Map valid class XP records by API class ID."""
    if not isinstance(value, list):
        return {}
    return {
        str(item["id"]): item["exp"]
        for item in value
        if isinstance(item, dict)
        and isinstance(item.get("id"), (int, str))
        and not isinstance(item.get("id"), bool)
        and isinstance(item.get("exp"), int)
        and not isinstance(item.get("exp"), bool)
        and item["exp"] >= 0
    }


def _bound_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Limit recorded list payloads and disclose the untruncated item count."""

    def bound(value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(item, list) and len(item) > 60:
                    result[key] = [bound(row) for row in item[-60:]]
                    result[f"{key}_total"] = len(item)
                    result[f"{key}_truncated"] = True
                else:
                    result[key] = bound(item)
            return result
        if isinstance(value, list):
            return [bound(item) for item in value]
        return value

    bounded = bound(attributes)

    def shrink_largest(value: Any, path: str = "attributes") -> bool:
        if isinstance(value, dict):
            lists = [
                (key, item)
                for key, item in value.items()
                if isinstance(item, list) and len(item) > 5
            ]
            if lists:
                key, rows = max(lists, key=lambda item: len(item[1]))
                value.setdefault(f"{key}_total", len(rows))
                value[f"{key}_truncated"] = True
                value[key] = rows[-max(5, len(rows) // 2) :]
                return True
            return any(shrink_largest(item, f"{path}.{key}") for key, item in value.items())
        if isinstance(value, list):
            return any(shrink_largest(item, path) for item in value)
        return False

    while len(json.dumps(bounded, default=str, separators=(",", ":"))) > 12_000:
        if not shrink_largest(bounded):
            break
    return bounded


def _rank_image_index(exp: object) -> int | None:
    """Map player EXP to the rank badge index used by the stats page."""
    if not isinstance(exp, int) or isinstance(exp, bool) or exp < 0:
        return None
    index = -1
    for candidate, threshold in enumerate(RANK_EXP_THRESHOLDS):
        if exp < threshold:
            break
        index = candidate
    return index if index >= 0 else None


def _class_exp_total(value: object) -> int | None:
    """Sum valid class XP values while keeping malformed data unknown."""
    if not isinstance(value, list):
        return None
    parsed = _class_exp_by_id(value)
    return sum(parsed.values())


def _named_class_exp(value: object) -> dict[str, int]:
    """Return class experience with preview API class IDs labeled for dashboards."""
    return {
        CLASS_NAMES.get(class_id, class_id): exp
        for class_id, exp in _class_exp_by_id(value).items()
    }


def _history_points(value: dict[str, Any], key: str) -> list[dict[str, Any]] | None:
    """Return a validated history point list from one independently polled source."""
    dataset = value.get(key)
    points = dataset.get("points") if isinstance(dataset, dict) else None
    return points if isinstance(points, list) else None


def _epoch_millis_to_iso(value: object) -> str | None:
    """Format a millisecond capture timestamp without converting invalid data."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _rate_limit_value(headers: dict[str, Any], *keys: str) -> str | None:
    """Return the first provided quota header without inventing a limit."""
    for key in keys:
        value = headers.get(key)
        if isinstance(value, str):
            return value
    return None


def _round_rows(value: object) -> list[dict[str, Any]] | None:
    """Keep breakdown attributes compact and display decimal statistics to two places."""
    if not isinstance(value, list):
        return None
    return [
        {
            key: round(item, 2) if isinstance(item, float) and isfinite(item) else item
            for key, item in row.items()
        }
        for row in value
        if isinstance(row, dict)
    ]
