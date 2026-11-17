"""Migration preserves identity and endpoint/entity selections are explicit."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

from homeassistant.helpers.entity_registry import RegistryEntryDisabler

from custom_components.blockfront import async_migrate_entry, async_setup_entry
from custom_components.blockfront.official import DEFAULT_URL
from custom_components.blockfront.official_runtime import catalog, selected
from custom_components.blockfront.sensor import VuisSensor

UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


async def test_migration_keeps_only_the_current_official_key_and_moves_to_vuis():
    entry = SimpleNamespace(
        version=4,
        data={
            "username": "denkz0ne",
            "player_uuid": UUID,
            "api_key": "official-key-from-v0.9.0",
            "api_base_url": DEFAULT_URL,
            "old_provider_key": "must-not-survive",
        },
        options={},
    )
    hass = MagicMock()
    assert await async_migrate_entry(hass, entry)
    saved = hass.config_entries.async_update_entry.call_args.kwargs
    assert saved["data"] == {
        "username": "denkz0ne",
        "player_uuid": UUID,
        "api_base_url": DEFAULT_URL,
    }
    assert saved["options"] == {"api_key": "official-key-from-v0.9.0"}
    assert saved["version"] == 5


def test_catalog_exposes_only_selected_vuis_families_and_preserves_unique_ids():
    rows = catalog()
    keys = {row["key"] for row in rows}
    assert {row["endpoint"] for row in rows} == {
        "vuis_profile",
        "vuis_matches",
        "vuis_brigade",
    }
    assert not keys.intersection(
        {
            "player_uuid",
            "captures",
            "commander_exp",
            "latest_match_duration",
            "match_axisCasualties",
            "match_alliedCasualties",
            "online_players",
            "monthly_score",
        }
    )

    entry = SimpleNamespace(
        data={"username": "denkz0ne", "player_uuid": UUID}, options={}
    )
    assert all(selected(entry, row) for row in rows)
    kills = next(row for row in rows if row["key"] == "kills")
    sensor = VuisSensor(MagicMock(), entry, kills)
    assert sensor.unique_id == f"{UUID}_kills"
    assert sensor.native_unit_of_measurement == "kills"

    entry.options["enabled_metrics"] = ["rank", "kills"]
    assert selected(entry, kills)
    assert not selected(entry, next(row for row in rows if row["key"] == "deaths"))


async def test_registry_disables_unsupported_entities_and_respects_user_choice():
    entry = MagicMock()
    entry.data = {"username": "denkz0ne", "player_uuid": UUID}
    entry.options = {}
    entry.entry_id = "entry"
    entities = [
        SimpleNamespace(
            unique_id=f"{UUID}_kills", entity_id="sensor.kills", disabled_by=None
        ),
        SimpleNamespace(
            unique_id=f"{UUID}_online_players", entity_id="sensor.online", disabled_by=None
        ),
        SimpleNamespace(
            unique_id=f"{UUID}_deaths",
            entity_id="sensor.deaths",
            disabled_by=RegistryEntryDisabler.USER,
        ),
        SimpleNamespace(
            unique_id=f"{UUID}_assists",
            entity_id="sensor.assists",
            disabled_by=RegistryEntryDisabler.INTEGRATION,
        ),
    ]
    registry = MagicMock()
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(return_value=catalog())
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.async_create_task.side_effect = lambda task, *args: (task.close(), MagicMock())[1]
    with (
        patch("custom_components.blockfront.er.async_get", return_value=registry),
        patch(
            "custom_components.blockfront.er.async_entries_for_config_entry",
            return_value=entities,
        ),
        patch("custom_components.blockfront.create_official_runtime", return_value={}),
    ):
        await async_setup_entry(hass, entry)
        assert registry.async_update_entity.call_args_list == [
            call("sensor.online", disabled_by=RegistryEntryDisabler.INTEGRATION),
            call("sensor.assists", disabled_by=None),
        ]
        entities[1].disabled_by = RegistryEntryDisabler.INTEGRATION
        entities[3].disabled_by = None
        registry.async_update_entity.reset_mock()

        entry.options = {"enabled_metrics": ["kills"]}
        await async_setup_entry(hass, entry)
        assert registry.async_update_entity.call_args_list == [
            call("sensor.assists", disabled_by=RegistryEntryDisabler.INTEGRATION)
        ]
