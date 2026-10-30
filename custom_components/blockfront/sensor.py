"""Stable compatible sensors and new official API metrics."""

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .official_runtime import selected

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = entry.runtime_data
    async_add_entities(
        [
            OfficialSensor(runtime["coordinators"][row["endpoint"]], entry, row)
            for row in runtime["catalog"]
            if row.get("platform") != "binary_sensor" and selected(entry, row)
        ]
    )


class OfficialSensor(CoordinatorEntity, SensorEntity):
    """Never change measurement identity when switching access modes."""

    def __init__(self, coordinator, entry, row):
        super().__init__(coordinator)
        self.row = row
        self._attr_unique_id = f"{entry.data['player_uuid']}_{row['key']}"
        self._attr_has_entity_name = True
        fields = {
            k: v
            for k, v in row.items()
            if k
            in {
                "key",
                "name",
                "translation_key",
                "icon",
                "native_unit_of_measurement",
                "state_class",
                "device_class",
            }
        }
        if row.get("diagnostic"):
            fields["entity_category"] = EntityCategory.DIAGNOSTIC
        self.entity_description = SensorEntityDescription(**fields)
        self._attr_device_info = DeviceInfo(
            identifiers={("blockfront", entry.data["player_uuid"])},
            name=entry.data["username"],
            manufacturer="BlockFront",
            model="Official API",
        )

    @property
    def available(self):
        return bool(
            self.row.get("diagnostic") or (self.coordinator.data is not None and super().available)
        )

    @property
    def native_value(self):
        if self.row.get("diagnostic"):
            return "available" if self.coordinator.last_update_success else "unavailable"
        data = self.coordinator.data or {}
        key = self.row.get("value_key", self.row["key"])
        if self.row["key"] == "online_players":
            key = "online_players"
        elif self.row["endpoint"] == "player_matches":
            key = self.row["key"]
        value = data.get("values", {}).get(key)
        if self.row["key"] in {"kd_ratio", "hs_kr"} and isinstance(value, (int, float)):
            return round(value, 2)
        return value

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attrs = dict(data.get("attributes", {}))
        attrs["endpoint"] = self.row["endpoint"]
        if self.row.get("diagnostic"):
            attrs["last_error"] = (
                str(self.coordinator.last_exception) if self.coordinator.last_exception else None
            )
        return attrs
