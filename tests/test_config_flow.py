from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront import async_migrate_entry
from custom_components.blockfront.api import PlayerNotFound
from custom_components.blockfront.const import (
    CONF_API_BASE_URL,
    CONF_API_KEY,
    CONF_PLAYER_UUID,
    CONF_USERNAME,
    DEFAULT_OPTIONS,
    DOMAIN,
)

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"
TEST_API_BASE_URL = "https://statistics.example.invalid/v1/"


@pytest.fixture(autouse=True)
def enable_custom_component(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in Home Assistant tests."""


@pytest.mark.asyncio
async def test_config_flow_resolves_username_and_creates_entry(hass) -> None:
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class,
        patch("custom_components.blockfront.coordinator.async_get_clientsession"),
        patch("custom_components.blockfront.coordinator.BlockFrontApi") as coordinator_api,
    ):
        api_class.return_value.async_resolve_player = AsyncMock(return_value=PLAYER_UUID)
        coordinator_api.return_value.polling_data.return_value = {
            "api_polling_status": "available",
            "api_rate_limit_remaining": None,
        }
        coordinator_api.return_value.async_get_player = AsyncMock(return_value={})
        coordinator_api.return_value.async_get_match_data = AsyncMock(return_value={"matches": []})
        coordinator_api.return_value.async_get_analytics = AsyncMock(return_value={})
        coordinator_api.return_value.async_get_cloud_data = AsyncMock(
            return_value={"players_online": 0, "game_player_count": {}}
        )
        coordinator_api.return_value.async_get_status = AsyncMock(
            return_value={
                "data": {
                    "status": "ok",
                    "playerData": True,
                    "datasets": {"online": {"stale": False}},
                },
                "meta": {"stale": False},
            }
        )
        coordinator_api.return_value.async_get_overview = AsyncMock(
            return_value={"online": {"playersOnline": 0}}
        )
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "denkz0ne",
                CONF_API_BASE_URL: TEST_API_BASE_URL,
                CONF_API_KEY: "test-key",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "denkz0ne"
    assert result["data"] == {
        CONF_USERNAME: "denkz0ne",
        CONF_PLAYER_UUID: PLAYER_UUID,
        CONF_API_BASE_URL: TEST_API_BASE_URL,
        CONF_API_KEY: "test-key",
    }
    api_class.assert_called_once()
    assert api_class.call_args.kwargs["api_base_url"] == TEST_API_BASE_URL
    assert api_class.call_args.kwargs["api_key"] == "test-key"


@pytest.mark.asyncio
async def test_config_flow_rejects_invalid_username_before_request(hass) -> None:
    with patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "not a valid name",
                CONF_API_BASE_URL: TEST_API_BASE_URL,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_USERNAME] == "invalid_username"
    api_class.assert_not_called()


@pytest.mark.asyncio
async def test_config_flow_shows_error_for_unknown_player(hass) -> None:
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class,
    ):
        api_class.return_value.async_resolve_player = AsyncMock(
            side_effect=PlayerNotFound("unknown player")
        )
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "unknownplayer",
                CONF_API_BASE_URL: TEST_API_BASE_URL,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_player"


@pytest.mark.asyncio
async def test_config_flow_prevents_duplicate_player_entry(hass) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="denkz0ne",
        unique_id=PLAYER_UUID,
        data={CONF_USERNAME: "denkz0ne", CONF_PLAYER_UUID: PLAYER_UUID},
    )
    existing.add_to_hass(hass)
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class,
    ):
        api_class.return_value.async_resolve_player = AsyncMock(return_value=PLAYER_UUID)
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "denkz0ne",
                CONF_API_BASE_URL: TEST_API_BASE_URL,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_options_flow_shows_independent_default_intervals(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="denkz0ne",
        unique_id=PLAYER_UUID,
        data={CONF_USERNAME: "denkz0ne", CONF_PLAYER_UUID: PLAYER_UUID},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    defaults = {
        marker.schema: marker.default() if callable(marker.default) else marker.default
        for marker in schema
    }
    assert defaults == {
        CONF_API_BASE_URL: "",
        CONF_API_KEY: "",
        **DEFAULT_OPTIONS,
    }


@pytest.mark.asyncio
async def test_migrate_entry_renames_legacy_api_key_without_losing_value(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="denkz0ne",
        unique_id=PLAYER_UUID,
        data={
            CONF_USERNAME: "denkz0ne",
            CONF_PLAYER_UUID: PLAYER_UUID,
            "legacy_api_key": "saved-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.data[CONF_API_KEY] == "saved-secret"
    assert "legacy_api_key" not in entry.data
    assert entry.version == 2
