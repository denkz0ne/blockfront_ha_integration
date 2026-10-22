from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.binary_sensor import BlockFrontBinarySensor
from custom_components.blockfront.const import CONF_PLAYER_UUID, CONF_USERNAME, DOMAIN
from custom_components.blockfront.sensor import (
    SENSOR_DESCRIPTIONS,
    BlockFrontProgressSensor,
    BlockFrontSensor,
    _bound_attributes,
)

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


def test_large_history_attributes_are_bounded_with_total_count() -> None:
    attributes = {"history_points": [{"index": index} for index in range(365)]}
    bounded = _bound_attributes(attributes)
    assert len(bounded["history_points"]) == 60
    assert bounded["history_points_total"] == 365
    assert bounded["history_points_truncated"] is True


def make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="denkz0ne",
        unique_id=PLAYER_UUID,
        data={CONF_USERNAME: "denkz0ne", CONF_PLAYER_UUID: PLAYER_UUID},
    )


def make_coordinator(hass, value: dict) -> DataUpdateCoordinator:
    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name="test",
        update_interval=timedelta(minutes=15),
    )
    coordinator.data = {
        "value": value,
        "updated_at": "2026-10-09T10:00:00+00:00",
        "last_successful_update": "2026-10-09T10:00:00+00:00",
        "last_attempt": "2026-10-09T10:00:00+00:00",
        "stale": False,
        "last_error": None,
    }
    return coordinator


def description(key: str):
    return next(item for item in SENSOR_DESCRIPTIONS if item.key == key)


def test_profile_sensor_uses_existing_value_and_keeps_missing_unknown(hass) -> None:
    coordinator = make_coordinator(hass, {"kills": 44, "deaths": None})
    kills = BlockFrontSensor(coordinator, make_entry(), description("kills"))
    deaths = BlockFrontSensor(coordinator, make_entry(), description("deaths"))

    assert kills.native_value == 44
    assert deaths.native_value is None


def test_player_sensor_friendly_name_starts_with_configured_username() -> None:
    sensor = BlockFrontSensor(
        make_coordinator(None, {"kills": 44}), make_entry(), description("kills")
    )
    sensor._attr_name = "Kills"

    assert sensor._friendly_name_internal() == "[denkz0ne] Kills"
    assert sensor.unique_id == f"{PLAYER_UUID}_kills"
    assert sensor.suggested_object_id == "Kills"


def test_global_sensor_friendly_name_does_not_include_username() -> None:
    sensor = BlockFrontSensor(
        make_coordinator(None, {"online_count": 8}), make_entry(), description("online_players")
    )
    sensor._attr_name = "Players online"

    assert sensor._friendly_name_internal() == "Players online"


def test_progress_sensor_friendly_name_starts_with_configured_username() -> None:
    sensor = BlockFrontProgressSensor(make_entry(), "kills")
    sensor._attr_name = "Kills since last observation"

    assert sensor._friendly_name_internal() == "[denkz0ne] Kills since last observation"
    assert sensor.unique_id == f"{PLAYER_UUID}_kills_since_observation"
    assert sensor.suggested_object_id == "Kills since last observation"


def test_binary_profile_sensor_friendly_name_starts_with_configured_username() -> None:
    sensor = BlockFrontBinarySensor(
        make_coordinator(None, {"bootcamp": True}),
        make_entry(),
        BinarySensorEntityDescription(key="bootcamp", translation_key="bootcamp"),
    )
    sensor._attr_name = "Bootcamp"

    assert sensor._friendly_name_internal() == "[denkz0ne] Bootcamp"
    assert sensor.unique_id == f"{PLAYER_UUID}_bootcamp"


def test_latest_match_sensor_exposes_display_attributes(hass) -> None:
    match = {
        "result": "loss",
        "ended_at": "2026-10-08T18:46:20Z",
        "map": "Ursprung",
        "game": "dom",
        "kills": 6,
        "deaths": 10,
        "assists": 0,
        "score": 14,
        "player_team": "Axis",
        "duration_seconds": 719,
        "match_id": "36a057d4-f91e-4714-a8e6-2a32ea15912b",
    }
    sensor = BlockFrontSensor(
        make_coordinator(hass, {"matches": [match]}),
        make_entry(),
        description("latest_match"),
    )

    assert sensor.native_value == "loss"
    assert sensor.extra_state_attributes["map"] == "Ursprung"
    assert sensor.extra_state_attributes["kills"] == 6
    assert sensor.extra_state_attributes["last_successful_update"]


def test_online_sensor_reports_fallback_source(hass) -> None:
    sensor = BlockFrontSensor(
        make_coordinator(
            hass,
            {
                "online_count": 79,
                "source": "official_website",
                "source_timestamp": None,
                "api_error": "Statistics API timed out",
            },
        ),
        make_entry(),
        description("online_players"),
    )

    assert sensor.native_value == 79
    assert sensor.extra_state_attributes["source"] == "official_website"


def test_service_sensor_exposes_stale_feed_diagnostics(hass) -> None:
    sensor = BlockFrontSensor(
        make_coordinator(
            hass,
            {
                "status": "degraded",
                "stale_feed_count": 2,
                "version": "1.2.3",
                "uptime_seconds": 420,
                "upstream_error": "upstream returned status 503",
            },
        ),
        make_entry(),
        description("service_status"),
    )

    assert sensor.native_value == "degraded"
    assert sensor.extra_state_attributes["stale_feed_count"] == 2
    assert sensor.extra_state_attributes["upstream_error"] == "upstream returned status 503"



def test_archive_sensor_retains_source_capture_and_stale_diagnostics(hass) -> None:
    archived = {
        "classes": {
            "items": [{"id": 0, "exp": 120}],
            "captured_at": 1720000000000,
            "source_timestamp": "2026-10-22T09:00:00Z",
            "source_stale": True,
            "source": "statistics_api_archive",
            "error": "HTTP 503",
        },
        "inventory": {
            "items": [{"name": "item"}],
            "captured_at": 1710000000000,
            "source_timestamp": "2026-10-20T09:00:00Z",
            "source_stale": False,
            "source": "statistics_api_archive",
            "error": None,
        },
    }
    coordinator = make_coordinator(hass, archived)
    classes = BlockFrontSensor(coordinator, make_entry(), description("class_exp"))
    inventory = BlockFrontSensor(coordinator, make_entry(), description("inventory_items"))

    assert classes.native_value == 120
    assert classes.extra_state_attributes["archive_source_stale"] is True
    assert classes.extra_state_attributes["archive_source_timestamp"] == "2026-10-22T09:00:00Z"
    assert classes.extra_state_attributes["archive_error"] == "HTTP 503"
    assert inventory.native_value == 1
    assert inventory.extra_state_attributes["archive_source_stale"] is False
    assert inventory.extra_state_attributes["archive_source_timestamp"] == "2026-10-20T09:00:00Z"


def test_online_sensor_exposes_selected_source_freshness(hass) -> None:
    sensor = BlockFrontSensor(
        make_coordinator(
            hass,
            {
                "online_count": 81,
                "source": "blockfront_official_api",
                "source_timestamp": None,
                "source_freshness": "unknown",
                "source_stale": None,
                "polling_status": "available",
                "fallback_errors": {"statistics_api": "timeout"},
            },
        ),
        make_entry(),
        description("online_players"),
    )

    assert sensor.native_value == 81
    assert sensor.extra_state_attributes["source_freshness"] == "unknown"
    assert sensor.extra_state_attributes["fallback_errors"] == {"statistics_api": "timeout"}
    assert sensor.extra_state_attributes["online_source"] == "blockfront_official_api"
    assert sensor.extra_state_attributes["online_source_captured_at"] is None
    assert sensor.extra_state_attributes["online_is_stale"] is None
    assert sensor.extra_state_attributes["online_polling_status"] == "available"
