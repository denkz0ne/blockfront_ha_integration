"""Migration preserves registry IDs and access transitions respect user choices."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers.entity_registry import RegistryEntryDisabler

from custom_components.blockfront import async_migrate_entry, async_setup_entry
from custom_components.blockfront.official import DEFAULT_URL
from custom_components.blockfront.official_runtime import catalog, selected
from custom_components.blockfront.sensor import OfficialSensor


async def test_migration_discards_other_provider_keys_not_identity():
    entry = SimpleNamespace(
        data={
            "username": "denkz0ne",
            "player_uuid": "stable-uuid",
            "api_key": "old-provider-key",
            "api_base_url": "https://old.invalid/",
        },
        options={"api_key": "old-options-key"},
    )
    hass = MagicMock()
    assert await async_migrate_entry(hass, entry)
    saved = hass.config_entries.async_update_entry.call_args.kwargs
    assert saved["data"] == {
        "username": "denkz0ne",
        "player_uuid": "stable-uuid",
        "api_base_url": DEFAULT_URL,
    }
    assert saved["options"] == {} and saved["version"] == 4


def test_private_entities_absent_without_key_and_same_identity_with_key():
    rows = catalog()
    entry = SimpleNamespace(data={"username": "denkz0ne", "player_uuid": "stable"}, options={})
    assert all(
        r["endpoint"] not in {"player", "player_matches", "clan", "match"}
        for r in rows
        if selected(entry, r)
    )
    entry.options = {"api_key": "official-test-key"}
    row = next(r for r in rows if r["key"] == "kills")
    assert selected(entry, row)
    sensor = OfficialSensor(MagicMock(), entry, row)
    assert sensor.unique_id == "stable_kills"
    assert sensor.native_unit_of_measurement == "kills"
    assert sensor.state_class == "total_increasing"
    entry.options["enabled_metrics"] = []
    assert not any(selected(entry, r) for r in rows)


async def test_registry_disable_and_reenable_preserves_user_disabled_entities():
    entry = MagicMock()
    entry.data = {"username": "denkz0ne", "player_uuid": "stable"}
    entry.options = {}
    entry.entry_id = "entry"
    entities = [
        SimpleNamespace(unique_id="stable_kills", entity_id="sensor.kills", disabled_by=None),
        SimpleNamespace(
            unique_id="stable_online_players",
            entity_id="sensor.online",
            disabled_by=RegistryEntryDisabler.USER,
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
            "custom_components.blockfront.er.async_entries_for_config_entry", return_value=entities
        ),
        patch("custom_components.blockfront.create_official_runtime", return_value={}),
    ):
        await async_setup_entry(hass, entry)
        registry.async_update_entity.assert_called_once_with(
            "sensor.kills", disabled_by=RegistryEntryDisabler.INTEGRATION
        )
        registry.async_remove.assert_not_called()
        registry.reset_mock()
        entities[0].disabled_by = RegistryEntryDisabler.INTEGRATION
        entry.options = {"api_key": "official-key"}
        await async_setup_entry(hass, entry)
        registry.async_update_entity.assert_called_once_with("sensor.kills", disabled_by=None)
