"""Player, match, brigade, and source status sensors."""

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
            VuisSensor(runtime["coordinators"][row["endpoint"]], entry, row)
            for row in runtime["catalog"]
            if row.get("platform") != "binary_sensor"
            and row["endpoint"] in runtime["coordinators"]
            and selected(entry, row)
        ]
    )


class VuisSensor(CoordinatorEntity, SensorEntity):
    """Expose normalized values while keeping player UUID-based identities."""

    def __init__(self, coordinator, entry, row):
        super().__init__(coordinator)
        self.row = row
        self._attr_unique_id = f"{entry.data['player_uuid']}_{row['key']}"
        self._attr_has_entity_name = True
        fields = {
            key: value
            for key, value in row.items()
            if key
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
            model="Vuis public stats with optional official API fallback",
        )

    @property
    def available(self):
        if self.row.get("diagnostic"):
            return True
        return self.coordinator.data is not None and super().available

    @property
    def native_value(self):
        if self.row.get("diagnostic"):
            return "available" if self.coordinator.last_update_success else "unavailable"
        key = self.row.get("value_key", self.row["key"])
        value = (self.coordinator.data or {}).get("values", {}).get(key)
        if value is None:
            return None
        if key == "kd_ratio":
            return round(value, 2)
        if key in {"rank_progress_percent", "win_rate"}:
            return round(value, 1)
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
