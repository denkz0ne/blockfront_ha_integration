"""BlockFront public statistics integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import BlockFrontConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: BlockFrontConfigEntry) -> bool:
    """Set up a BlockFront player and its independently polled sensor groups."""
    from .config_flow import async_reload_entry
    from .const import PLATFORMS
    from .coordinator import create_runtime

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
