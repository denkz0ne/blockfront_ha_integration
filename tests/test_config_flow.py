from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.api import PlayerNotFound
from custom_components.blockfront.const import (
    CONF_PLAYER_UUID,
    CONF_USERNAME,
    DEFAULT_OPTIONS,
    DOMAIN,
)

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


@pytest.fixture(autouse=True)
def enable_custom_component(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in Home Assistant tests."""


@pytest.mark.asyncio
async def test_config_flow_resolves_username_and_creates_entry(hass) -> None:
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class,
    ):
        api_class.return_value.async_resolve_player = AsyncMock(return_value=PLAYER_UUID)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_USERNAME: "denkz0ne"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "denkz0ne"
    assert result["data"] == {CONF_USERNAME: "denkz0ne", CONF_PLAYER_UUID: PLAYER_UUID}


@pytest.mark.asyncio
async def test_config_flow_rejects_invalid_username_before_request(hass) -> None:
    with patch("custom_components.blockfront.config_flow.BlockFrontApi") as api_class:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_USERNAME: "not a valid name"}
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
        api_class.return_value.async_resolve_player = AsyncMock(side_effect=PlayerNotFound)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_USERNAME: "unknownplayer"}
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
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_USERNAME: "denkz0ne"}
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
        marker.schema: marker.default()() if callable(marker.default) else marker.default
        for marker in schema
    }
    assert defaults == DEFAULT_OPTIONS
