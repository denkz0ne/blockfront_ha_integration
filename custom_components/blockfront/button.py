"""Refresh the enabled official datasets."""

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OfficialRefresh(entry)])


class OfficialRefresh(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh_all"

    def __init__(self, entry):
        self._entry = entry
        self._attr_unique_id = f"{entry.data['player_uuid']}_refresh_all"
        self._attr_device_info = DeviceInfo(identifiers={("blockfront", entry.data["player_uuid"])})

    async def async_press(self):
        for coordinator in self._entry.runtime_data["coordinators"].values():
            await coordinator.async_request_refresh()
