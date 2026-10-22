from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.api import ApiError
from custom_components.blockfront.const import (
    CONF_PLAYER_UUID,
    CONF_USERNAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPTION_ONLINE_INTERVAL,
    OPTION_PROFILE_INTERVAL,
    get_update_interval,
)
from custom_components.blockfront.coordinator import BlockFrontCoordinator

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


def make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="denkz0ne",
        unique_id=PLAYER_UUID,
        data={CONF_USERNAME: "denkz0ne", CONF_PLAYER_UUID: PLAYER_UUID},
    )


@pytest.mark.asyncio
async def test_profile_failure_preserves_last_good_value(hass) -> None:
    async def fail_fetch() -> dict:
        raise ApiError("upstream unavailable")

    coordinator = BlockFrontCoordinator(
        hass,
        make_entry(),
        "profile",
        timedelta(minutes=15),
        fail_fetch,
        {"value": None},
    )
    coordinator.data = {
        "value": {"kills": 14},
        "updated_at": "2026-10-09T10:00:00+00:00",
        "last_successful_update": "2026-10-09T10:00:00+00:00",
        "stale": False,
        "last_error": None,
    }

    data = await coordinator._async_update_data()

    assert data["value"] == {"kills": 14}
    assert data["stale"] is True
    assert data["last_error"] == "upstream unavailable"
    assert data["last_successful_update"] == "2026-10-09T10:00:00+00:00"


@pytest.mark.asyncio
async def test_status_request_failure_marks_service_unavailable(hass) -> None:
    async def fail_fetch() -> dict:
        raise ApiError("status endpoint timeout")

    coordinator = BlockFrontCoordinator(
        hass,
        make_entry(),
        "status",
        timedelta(minutes=15),
        fail_fetch,
        {"value": {"status": "unavailable", "stale_feed_count": 0}},
    )

    data = await coordinator._async_update_data()

    assert data["value"]["status"] == "unavailable"
    assert data["stale"] is True
    assert data["last_error"] == "status endpoint timeout"


def test_default_poll_intervals_are_independent() -> None:
    profile = get_update_interval(DEFAULT_OPTIONS, "profile")
    online = get_update_interval(DEFAULT_OPTIONS, "online")
    assert profile == timedelta(minutes=15)
    assert online == timedelta(minutes=5)
    assert profile != online


def test_poll_intervals_are_clamped_to_safe_bounds() -> None:
    options = {**DEFAULT_OPTIONS, OPTION_PROFILE_INTERVAL: 1, OPTION_ONLINE_INTERVAL: 999_999}
    assert get_update_interval(options, "profile") == timedelta(minutes=5)
    assert get_update_interval(options, "online") == timedelta(hours=24)



@pytest.mark.asyncio
async def test_archive_partial_error_keeps_last_good_snapshot(hass) -> None:
    async def partial_fetch() -> dict:
        return {
            "classes": {
                "items": [{"id": 0, "exp": 50}],
                "captured_at": 2000,
                "source_timestamp": "2026-10-22T10:00:00Z",
                "source_stale": False,
                "error": None,
            },
            "inventory": {
                "items": None,
                "captured_at": None,
                "source_timestamp": None,
                "source_stale": True,
                "error": "HTTP 404",
            },
            "source_stale": True,
        }

    coordinator = BlockFrontCoordinator(
        hass, make_entry(), "archive", timedelta(hours=6), partial_fetch, {"value": None}
    )
    coordinator.data = {
        "value": {
            "classes": {
                "items": [{"id": 0, "exp": 20}],
                "captured_at": 1000,
                "source_timestamp": "2026-10-21T10:00:00Z",
                "source_stale": False,
                "error": None,
            },
            "inventory": {
                "items": [{"name": "saved_item"}],
                "captured_at": 1500,
                "source_timestamp": "2026-10-21T11:00:00Z",
                "source_stale": False,
                "error": None,
            },
        },
        "updated_at": "2026-10-21T11:00:00Z",
    }

    result = await coordinator._async_update_data()

    assert result["value"]["classes"]["items"] == [{"id": 0, "exp": 50}]
    assert result["value"]["inventory"]["items"] == [{"name": "saved_item"}]
    assert result["value"]["inventory"]["captured_at"] == 1500
    assert result["value"]["inventory"]["source_timestamp"] == "2026-10-21T11:00:00Z"
    assert result["value"]["inventory"]["source_stale"] is True
    assert result["value"]["inventory"]["error"] == "HTTP 404"
    assert result["stale"] is True


@pytest.mark.asyncio
async def test_online_success_with_unknown_source_age_is_not_misreported_as_outage(hass) -> None:
    async def fetch_online() -> dict:
        return {
            "online_count": 91,
            "polling_status": "available",
            "source": "official_website",
            "source_timestamp": None,
            "source_stale": None,
        }

    coordinator = BlockFrontCoordinator(
        hass, make_entry(), "online", timedelta(minutes=5), fetch_online, {"value": None}
    )
    result = await coordinator._async_update_data()

    assert result["value"]["online_count"] == 91
    assert result["stale"] is False
    assert result["value"]["source_timestamp"] is None
    assert result["value"]["online_last_successful_update"]
    assert "cloud_last_successful_update" not in result["value"]


@pytest.mark.asyncio
async def test_online_failure_retains_last_count_with_stale_flag(hass) -> None:
    async def fail_online() -> dict:
        raise ApiError("all online sources failed")

    coordinator = BlockFrontCoordinator(
        hass, make_entry(), "online", timedelta(minutes=5), fail_online, {"value": None}
    )
    coordinator.data = {
        "value": {
            "online_count": 72,
            "source": "statistics_api",
            "source_timestamp": "2026-10-22T12:00:00Z",
            "polling_status": "available",
        },
        "last_successful_update": "2026-10-22T12:00:00Z",
    }
    result = await coordinator._async_update_data()

    assert result["value"]["online_count"] == 72
    assert result["value"]["source_timestamp"] == "2026-10-22T12:00:00Z"
    assert result["stale"] is True
    assert result["value"]["polling_status"] == "unavailable"
