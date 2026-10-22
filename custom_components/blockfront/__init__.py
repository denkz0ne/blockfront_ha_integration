"""BlockFront public statistics integration."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import BlockFrontConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled rank images to Home Assistant's frontend."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("static_paths_registered"):
        assets_path = Path(__file__).parent / "assets"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/api/blockfront/icons",
                    str(assets_path),
                    cache_headers=True,
                )
            ]
        )
        domain_data["static_paths_registered"] = True
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate saved API-key field names without retaining provider branding."""
    data = dict(entry.data)
    options = dict(entry.options)
    legacy_keys = {
        key
        for store in (data, options)
        for key in store
        if key.endswith("_api_key") and key != "api_key"
    }
    if "api_key" not in options and "api_key" not in data:
        for store in (options, data):
            legacy_key = next((key for key in legacy_keys if key in store), None)
            if legacy_key is not None:
                store["api_key"] = store[legacy_key]
                break
    for store in (data, options):
        for key in legacy_keys:
            store.pop(key, None)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BlockFrontConfigEntry) -> bool:
    """Set up a BlockFront player and its independently polled sensor groups."""
    from .config_flow import async_reload_entry
    from .const import PLATFORMS
    from .coordinator import create_runtime

    removed_mode_sensors = {
        "cloud_bootcamp_players",
        "cloud_domination_players",
        "cloud_offensive_players",
        "cloud_defusal_players",
        "cloud_team_deathmatch_players",
        "cloud_gun_game_players",
        "cloud_free_for_all_players",
        "cloud_infected_players",
        "cloud_trouble_town_players",
    }
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if any(entity.unique_id.endswith(f"_{key}") for key in removed_mode_sensors):
            registry.async_remove(entity.entity_id)

    runtime = create_runtime(hass, entry)
    entry.runtime_data = runtime

    await asyncio.gather(
        *(coordinator.async_refresh() for coordinator in runtime.coordinators.values())
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BlockFrontConfigEntry) -> bool:
    """Unload integration platforms."""
    from .const import PLATFORMS

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
