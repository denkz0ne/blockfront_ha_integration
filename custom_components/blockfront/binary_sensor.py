"""Optional official profile boolean, with its original entity identity."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .official_runtime import selected

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    rows = [
        r
        for r in entry.runtime_data["catalog"]
        if r.get("platform") == "binary_sensor" and selected(entry, r)
    ]
    async_add_entities([OfficialBootcamp(entry) for row in rows])


class OfficialBootcamp(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "bootcamp"
    _attr_icon = "mdi:school"

    def __init__(self, entry):
        super().__init__(entry.runtime_data["coordinators"]["player"])
        self._attr_unique_id = f"{entry.data['player_uuid']}_bootcamp"
        self._attr_device_info = DeviceInfo(identifiers={("blockfront", entry.data["player_uuid"])})

    @property
    def is_on(self):
        return (self.coordinator.data or {}).get("values", {}).get("bootcamp")
