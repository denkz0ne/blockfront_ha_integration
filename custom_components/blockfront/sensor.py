"""Sensors for BlockFront player statistics and service status."""

from __future__ import annotations

from dataclasses import dataclass
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
ICON_BASE_PATH = "/api/blockfront/icons"


@dataclass(frozen=True, kw_only=True)
class BlockFrontSensorDescription(SensorEntityDescription):
    """Add a coordinator and value key to a Home Assistant sensor description."""

    coordinator_key: str
    value_key: str | None = None
    game_mode: str | None = None


SENSOR_DESCRIPTIONS = (
    BlockFrontSensorDescription(
        key="kills", translation_key="kills", coordinator_key="profile", value_key="kills",
        icon="mdi:target",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="deaths", translation_key="deaths", coordinator_key="profile", value_key="deaths",
        icon="mdi:skull",
        native_unit_of_measurement="deaths",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="kd_ratio", translation_key="kd_ratio", coordinator_key="profile", value_key="kd",
        icon="mdi:scale-balance",
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="head_shots", translation_key="head_shots", coordinator_key="profile",
        value_key="head_shots",
        icon="mdi:crosshairs",
        native_unit_of_measurement="headshots",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="first_bloods", translation_key="first_bloods", coordinator_key="profile",
        value_key="first_bloods",
        icon="mdi:water",
        native_unit_of_measurement="first bloods",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="no_scopes", translation_key="no_scopes", coordinator_key="profile",
        value_key="no_scopes",
        icon="mdi:scope",
        native_unit_of_measurement="no-scopes",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="total_games", translation_key="total_games", coordinator_key="profile",
        value_key="total_games",
        icon="mdi:gamepad-variant",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="time_played", translation_key="time_played", coordinator_key="profile",
        value_key="time_played",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="rank", translation_key="rank", coordinator_key="profile", value_key="rank",
        icon="mdi:medal",
    ),
    BlockFrontSensorDescription(
        key="prestige", translation_key="prestige", coordinator_key="profile",
        value_key="prestige",
        icon="mdi:star-circle",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="assists", translation_key="assists", coordinator_key="profile", value_key="assists",
        icon="mdi:handshake",
        native_unit_of_measurement="assists",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="back_stabs", translation_key="back_stabs", coordinator_key="profile",
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
        key="captures", translation_key="captures", coordinator_key="profile", value_key="captures",
        icon="mdi:flag-checkered",
        native_unit_of_measurement="captures",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="exp", translation_key="exp", coordinator_key="profile", value_key="exp",
        icon="mdi:star-four-points",
        native_unit_of_measurement="XP",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="class_exp", translation_key="class_exp", coordinator_key="profile",
        value_key="class_exp",
        icon="mdi:account-star",
        native_unit_of_measurement="XP",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="fire_kills", translation_key="fire_kills", coordinator_key="profile",
        value_key="fire_kills",
        icon="mdi:fire",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="heal_assists", translation_key="heal_assists", coordinator_key="profile",
        value_key="heal_assists",
        icon="mdi:medical-bag",
        native_unit_of_measurement="assists",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="highest_death_streak", translation_key="highest_death_streak",
        coordinator_key="profile", value_key="highest_death_streak",
        icon="mdi:skull-crossbones",
        native_unit_of_measurement="deaths",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="highest_kill_streak", translation_key="highest_kill_streak",
        coordinator_key="profile", value_key="highest_kill_streak",
        icon="mdi:fire-circle",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="hs_kr", translation_key="hs_kr", coordinator_key="profile", value_key="hs_kr",
        icon="mdi:crosshairs-gps",
        suggested_display_precision=2,
    ),
    BlockFrontSensorDescription(
        key="infected_kills", translation_key="infected_kills", coordinator_key="profile",
        value_key="infected_kills",
        icon="mdi:zombie",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="infected_matches_won", translation_key="infected_matches_won",
        coordinator_key="profile", value_key="infected_matches_won",
        icon="mdi:trophy",
        native_unit_of_measurement="matches",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="infected_rounds_won", translation_key="infected_rounds_won",
        coordinator_key="profile", value_key="infected_rounds_won",
        icon="mdi:check-decagram",
        native_unit_of_measurement="rounds",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="match_karma", translation_key="match_karma", coordinator_key="profile",
        value_key="match_karma",
        icon="mdi:heart",
        native_unit_of_measurement="karma",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="objective_score", translation_key="objective_score", coordinator_key="profile",
        value_key="objective_score",
        icon="mdi:flag",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="trophies", translation_key="trophies", coordinator_key="profile", value_key="trophies",
        icon="mdi:trophy-variant",
        native_unit_of_measurement="trophies",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="vehicle_kills", translation_key="vehicle_kills", coordinator_key="profile",
        value_key="vehicle_kills",
        icon="mdi:car",
        native_unit_of_measurement="kills",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    BlockFrontSensorDescription(
        key="skill_rank", translation_key="skill_rank", coordinator_key="profile",
        value_key="skill_rank",
        icon="mdi:medal-outline",
    ),
    BlockFrontSensorDescription(
        key="clan", translation_key="clan", coordinator_key="profile", value_key="clan",
        icon="mdi:account-group",
    ),
    BlockFrontSensorDescription(
        key="latest_match", translation_key="latest_match", coordinator_key="matches",
        icon="mdi:clipboard-text-clock",
    ),
    BlockFrontSensorDescription(
        key="latest_match_score", translation_key="latest_match_score",
        coordinator_key="matches", value_key="score",
        icon="mdi:counter",
        native_unit_of_measurement="points",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="online_players", translation_key="online_players", coordinator_key="online",
        value_key="online_count",
        icon="mdi:account-group",
        native_unit_of_measurement="players",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_bootcamp_players", translation_key="cloud_bootcamp_players",
        coordinator_key="online", game_mode="boot", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_domination_players", translation_key="cloud_domination_players",
        coordinator_key="online", game_mode="dom", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_offensive_players", translation_key="cloud_offensive_players",
        coordinator_key="online", game_mode="of", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_defusal_players", translation_key="cloud_defusal_players",
        coordinator_key="online", game_mode="def", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_team_deathmatch_players", translation_key="cloud_team_deathmatch_players",
        coordinator_key="online", game_mode="tdm", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_gun_game_players", translation_key="cloud_gun_game_players",
        coordinator_key="online", game_mode="gg", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_free_for_all_players", translation_key="cloud_free_for_all_players",
        coordinator_key="online", game_mode="ffa", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_infected_players", translation_key="cloud_infected_players",
        coordinator_key="online", game_mode="inf", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_trouble_town_players", translation_key="cloud_trouble_town_players",
        coordinator_key="online", game_mode="ttt", icon="mdi:account-group",
        native_unit_of_measurement="players", state_class=SensorStateClass.MEASUREMENT,
    ),
    BlockFrontSensorDescription(
        key="cloud_polling_status", translation_key="cloud_polling_status",
        coordinator_key="online", value_key="polling_status", icon="mdi:cloud-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BlockFrontSensorDescription(
        key="service_status", translation_key="service_status", coordinator_key="status",
        value_key="status",
        icon="mdi:server-network",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

_MATCH_ATTRIBUTE_KEYS = (
    "ended_at",
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
        BlockFrontSensor(
            entry.runtime_data.coordinators[description.coordinator_key],
            entry,
            description,
        )
        for description in SENSOR_DESCRIPTIONS
    )


class BlockFrontSensor(CoordinatorEntity[BlockFrontCoordinator], SensorEntity):
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
        self._username = entry.data[CONF_USERNAME]
        self._attr_unique_id = f"{player_uuid}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, player_uuid)},
            name=self._username,
            manufacturer="BlockFront",
            model="Player statistics",
        )

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
            if (
                isinstance(index, int)
                and not isinstance(index, bool)
                and 0 <= index <= 16
            ):
                return f"{ICON_BASE_PATH}/skill_ranks/{index}.png"
            return f"{ICON_BASE_PATH}/skill_ranks/none.png"

        if self.entity_description.key == "rank":
            index = _rank_image_index(profile.get("exp"))
            if index is not None:
                return f"{ICON_BASE_PATH}/ranks/{index}.png"
        return None

    @property
    def native_value(self) -> str | int | float | None:
        """Return a validated state value without inventing missing values."""
        data = self.coordinator.data or {}
        value = data.get("value")
        if not isinstance(value, dict):
            return None

        if self.entity_description.coordinator_key == "matches":
            matches = value.get("matches")
            if not isinstance(matches, list) or not matches:
                return None
            if self.entity_description.key == "latest_match_score":
                result = matches[0].get("score")
                if isinstance(result, (int, float)) and not isinstance(result, bool):
                    return result
                return None
            result = matches[0].get("result")
            return result if isinstance(result, str) and result else None

        if self.entity_description.game_mode is not None:
            counts = value.get("game_player_count")
            if not isinstance(counts, dict):
                return None
            result = counts.get(self.entity_description.game_mode)
            if isinstance(result, int) and not isinstance(result, bool) and result >= 0:
                return result
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
            return round(value, 2)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose match detail, source, and update health as state attributes."""
        coordinator_data = self.coordinator.data or {}
        attributes: dict[str, Any] = {
            "last_successful_update": coordinator_data.get("last_successful_update"),
            "last_attempt": coordinator_data.get("last_attempt"),
            "stale": coordinator_data.get("stale", True),
            "last_error": coordinator_data.get("last_error"),
        }
        value = coordinator_data.get("value")
        if not isinstance(value, dict):
            return attributes

        key = self.entity_description.coordinator_key
        if key == "profile":
            if self.entity_description.value_key == "class_exp":
                attributes["class_exp"] = _class_exp_by_id(value.get("class_exp"))
            elif self.entity_description.value_key == "skill_rank":
                skill_rank = value.get("skill_rank")
                if isinstance(skill_rank, dict):
                    attributes.update(
                        {
                            "skill_rank_index": skill_rank.get("index"),
                            "skill_rank_color": skill_rank.get("color"),
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
        elif key == "online":
            rate_limit = value.get("rate_limit")
            if not isinstance(rate_limit, dict):
                rate_limit = {}
            attributes.update(
                {
                    "source": value.get("source"),
                    "source_timestamp": value.get("source_timestamp"),
                    "api_error": value.get("api_error"),
                    "cloud_polling_status": value.get("polling_status"),
                    "cloud_stale": value.get("polling_status") != "available",
                    "cloud_last_successful_update": value.get(
                        "cloud_last_successful_update"
                    ),
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
                    "scoreboard_reset_time": value.get("scoreboard_reset_time"),
                    "players_by_game_mode": value.get("game_player_count"),
                }
            )
            if self.entity_description.key == "cloud_polling_status":
                attributes["poll_interval_seconds"] = int(
                    self.coordinator.update_interval.total_seconds()
                )
            if self.entity_description.game_mode is not None:
                attributes["game_mode"] = self.entity_description.game_mode
                attributes["players_online"] = value.get("online_count")
        elif key == "status":
            attributes.update(
                {
                    "stale_feed_count": value.get("stale_feed_count"),
                    "api_version": value.get("version"),
                    "service_uptime_seconds": value.get("uptime_seconds"),
                    "upstream_error": value.get("upstream_error"),
                }
            )
        return attributes


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


def _rate_limit_value(headers: dict[str, Any], *keys: str) -> str | None:
    """Return the first provided quota header without inventing a limit."""
    for key in keys:
        value = headers.get(key)
        if isinstance(value, str):
            return value
    return None
