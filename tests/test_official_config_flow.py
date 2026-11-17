"""Exercise username-first setup and optional official API behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.official import DEFAULT_URL

UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """Allow HA to discover the custom config flow."""


async def test_setup_resolves_uuid_without_optional_uuid_or_api_key(hass):
    session = MagicMock()
    with (
        patch(
            "custom_components.blockfront.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.blockfront.config_flow.resolve_player",
            new=AsyncMock(return_value=("denkz0ne", UUID)),
        ) as resolve_player,
        patch("custom_components.blockfront.config_flow.OfficialApi") as api_class,
        patch("custom_components.blockfront.async_setup_entry", return_value=True),
    ):
        flow = await hass.config_entries.flow.async_init(
            "blockfront", context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                "username": "denkz0ne",
                "player_uuid": "",
                "api_base_url": DEFAULT_URL,
                "api_key": "",
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "denkz0ne"
        assert result["data"]["player_uuid"] == UUID
        resolve_player.assert_awaited_once_with(session, "denkz0ne")
        api_class.assert_not_called()


async def test_options_validate_optional_key_and_preserve_metric_selection(hass):
    entry = MockConfigEntry(
        domain="blockfront",
        version=5,
        data={"username": "denkz0ne", "player_uuid": UUID, "api_base_url": DEFAULT_URL},
        options={"enabled_metrics": ["kills"]},
    )
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    submitted = form["data_schema"](
        {
            "api_base_url": DEFAULT_URL,
            "api_key": "official-test-key",
            "enabled_metrics": ["kills", "rank"],
            "vuis_profile_interval": 900,
            "vuis_matches_interval": 900,
            "vuis_brigade_interval": 1800,
        }
    )
    session = MagicMock()
    with (
        patch(
            "custom_components.blockfront.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch("custom_components.blockfront.config_flow.OfficialApi") as api_class,
    ):
        api_class.return_value.get = AsyncMock(return_value={"stats": {}})
        result = await hass.config_entries.options.async_configure(form["flow_id"], submitted)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["api_key"] == "official-test-key"
    assert entry.options["enabled_metrics"] == ["kills", "rank"]
    api_class.return_value.get.assert_awaited_once_with("player", uuid=UUID)

    form = await hass.config_entries.options.async_init(entry.entry_id)
    submitted = form["data_schema"]({"remove_api_key": True})
    result = await hass.config_entries.options.async_configure(form["flow_id"], submitted)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["api_key"] == ""
    assert entry.options["enabled_metrics"] == ["kills", "rank"]


async def test_setup_registers_selected_vuis_entities_without_official_key(hass):
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain="blockfront",
        version=5,
        unique_id=UUID,
        data={"username": "denkz0ne", "player_uuid": UUID, "api_base_url": DEFAULT_URL},
        options={"enabled_metrics": ["kills"]},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.blockfront.official_runtime.async_get_clientsession"),
        patch(
            "custom_components.blockfront.official_runtime.VuisCoordinator._async_update_data",
            new=AsyncMock(
                return_value={"values": {"kills": 17}, "attributes": {"source": "vuis.dev"}}
            ),
        ),
        patch("custom_components.blockfront.official_runtime.OfficialApi.get") as official_get,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        kills_id = registry.async_get_entity_id("sensor", "blockfront", f"{UUID}_kills")
        assert hass.states.get(kills_id).state == "17"
        online_id = registry.async_get_entity_id(
            "sensor", "blockfront", f"{UUID}_online_players"
        )
        assert online_id is None
        official_get.assert_not_called()
        assert await hass.config_entries.async_unload(entry.entry_id)
