"""Exercise HA's real flows, including automatic key-dependent activation."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blockfront.official import DEFAULT_URL

UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


@pytest.fixture(autouse=True)
def custom_integration(enable_custom_integrations):
    """Allow HA to discover the custom config flow."""


async def test_public_config_never_calls_private_endpoint(hass):
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.OfficialApi") as api_class,
        patch("custom_components.blockfront.async_setup_entry", return_value=True),
    ):
        api_class.return_value.api_key = ""
        api_class.return_value.get = AsyncMock(return_value={"playersOnline": 20})
        flow = await hass.config_entries.flow.async_init("blockfront", context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                "username": "denkz0ne",
                "player_uuid": UUID,
                "api_base_url": DEFAULT_URL,
                "api_key": "",
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["player_uuid"] == UUID
        api_class.return_value.get.assert_awaited_once_with("player_count")


async def test_options_add_and_remove_key_preserve_metric_selection(hass):
    entry = MockConfigEntry(
        domain="blockfront",
        version=4,
        data={"username": "denkz0ne", "player_uuid": UUID, "api_base_url": DEFAULT_URL},
    )
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    submitted = form["data_schema"](
        {"api_key": "official-test-key", "enabled_metrics": ["online_players"]}
    )
    with (
        patch("custom_components.blockfront.config_flow.async_get_clientsession"),
        patch("custom_components.blockfront.config_flow.OfficialApi") as api_class,
    ):
        api_class.return_value.get = AsyncMock(return_value={"stats": {}})
        result = await hass.config_entries.options.async_configure(form["flow_id"], submitted)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["api_key"] == "official-test-key"
    assert "kills" in entry.options["enabled_metrics"]

    assert "online_players" in entry.options["enabled_metrics"]
    form = await hass.config_entries.options.async_init(entry.entry_id)
    submitted = form["data_schema"]({"remove_api_key": True})
    result = await hass.config_entries.options.async_configure(form["flow_id"], submitted)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["api_key"] == ""
    assert "kills" in entry.options["enabled_metrics"]


async def test_real_public_setup_registers_only_public_entities(hass):
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain="blockfront",
        version=4,
        unique_id=UUID,
        data={"username": "denkz0ne", "player_uuid": UUID, "api_base_url": DEFAULT_URL},
        options={"enabled_metrics": ["online_players", "monthly_score", "kills"]},
    )
    entry.add_to_hass(hass)

    async def payload(endpoint, **params):
        return (
            {"playersOnline": 17}
            if endpoint == "player_count"
            else {"player": {"rank": 12, "score": 488}}
        )

    with (
        patch("custom_components.blockfront.official_runtime.async_get_clientsession"),
        patch(
            "custom_components.blockfront.official_runtime.OfficialApi.get", side_effect=payload
        ) as get,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        online_id = registry.async_get_entity_id("sensor", "blockfront", f"{UUID}_online_players")
        assert hass.states.get(online_id).state == "17"
        assert registry.async_get_entity_id("sensor", "blockfront", f"{UUID}_kills") is None
        assert {call.args[0] for call in get.call_args_list} == {"player_count", "scoreboard"}
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_authorized_setup_keeps_legacy_ids_and_discovers_new_fields(hass):
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain="blockfront",
        version=4,
        unique_id=UUID,
        data={"username": "denkz0ne", "player_uuid": UUID, "api_base_url": DEFAULT_URL},
        options={
            "api_key": "official-key",
            "enabled_metrics": ["kills", "official_stat_extraPoints"],
        },
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.blockfront.official_runtime.async_get_clientsession"),
        patch(
            "custom_components.blockfront.official_runtime.OfficialApi.get",
            new=AsyncMock(return_value={"stats": {"kills": 100, "extraPoints": 77}}),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        for key, expected in (("kills", "100"), ("official_stat_extraPoints", "77")):
            entity_id = registry.async_get_entity_id("sensor", "blockfront", f"{UUID}_{key}")
            assert hass.states.get(entity_id).state == expected
        assert await hass.config_entries.async_unload(entry.entry_id)
