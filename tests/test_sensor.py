from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.const import CONF_PLAYER_UUID, CONF_USERNAME, DOMAIN
from custom_components.blockfront.sensor import SENSOR_DESCRIPTIONS, BlockFrontSensor

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


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
                "api_error": "Blocklytics timed out",
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
