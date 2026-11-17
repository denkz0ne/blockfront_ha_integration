"""BlockFront statistics using Vuis public pages and optional official API data."""

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .official import DEFAULT_URL, normalize_url
from .official_runtime import catalog, create_official_runtime, selected
from .vuis import VuisError, resolve_player

DOMAIN = "blockfront"
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass, entry):
    """Move official API keys safely and resolve missing UUIDs through public Vuis data."""
    data = {key: entry.data[key] for key in ("username", "player_uuid") if key in entry.data}
    options = {}
    if entry.version >= 4:
        api_key = entry.options.get("api_key") or entry.data.get("api_key", "")
        try:
            api_base_url = normalize_url(
                entry.options.get("api_base_url")
                or entry.data.get("api_base_url", DEFAULT_URL)
            )
        except ValueError:
            api_base_url = DEFAULT_URL
        if api_key:
            options["api_key"] = api_key
        data["api_base_url"] = api_base_url
    else:
        # Previous-provider credentials are intentionally never forwarded.
        data["api_base_url"] = DEFAULT_URL
    if not data.get("player_uuid") and data.get("username"):
        try:
            username, identity = await resolve_player(
                async_get_clientsession(hass), data["username"]
            )
        except (VuisError, ValueError):
            return False
        data.update(username=username, player_uuid=identity)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=5)
    return True


async def async_setup_entry(hass, entry):
    rows = await hass.async_add_executor_job(catalog)
    runtime = create_official_runtime(hass, entry, rows)
    entry.runtime_data = {"coordinators": runtime, "catalog": rows}
    registry = er.async_get(hass)
    uuid = entry.data["player_uuid"]
    supported = {f"{uuid}_{row['key']}": row for row in rows}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        row = supported.get(entity.unique_id)
        enabled = row is not None and selected(entry, row)
        if not enabled and entity.disabled_by is None:
            registry.async_update_entity(
                entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
            )
        elif enabled and entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def refresh():
        for coordinator in runtime.values():
            await coordinator.async_refresh()

    task = hass.async_create_task(refresh(), "blockfront_official_initial_refresh")
    entry.async_on_unload(task.cancel)
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(
        entry, [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
    )
