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
