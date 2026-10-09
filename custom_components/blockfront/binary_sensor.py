"""Boolean profile sensors for BlockFront."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PLAYER_UUID, CONF_USERNAME, DOMAIN
from .coordinator import BlockFrontConfigEntry, BlockFrontCoordinator

PARALLEL_UPDATES = 0

BINARY_SENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="bootcamp",
        translation_key="bootcamp",
        icon="mdi:school",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BlockFrontConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create boolean profile entities."""
    coordinator = entry.runtime_data.coordinators["profile"]
    async_add_entities(
        BlockFrontBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class BlockFrontBinarySensor(
    CoordinatorEntity[BlockFrontCoordinator], BinarySensorEntity
):
    """Represent a boolean BlockFront profile field."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: BlockFrontCoordinator,
        entry: ConfigEntry,
        description: BinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        player_uuid = entry.data[CONF_PLAYER_UUID]
        self._attr_unique_id = f"{player_uuid}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, player_uuid)},
            name=entry.data[CONF_USERNAME],
            manufacturer="BlockFront",
            model="Player statistics",
        )

    @property
    def is_on(self) -> bool | None:
        """Return the upstream boolean, or unknown when it is missing."""
        value = (self.coordinator.data or {}).get("value")
        if not isinstance(value, dict):
            return None
        bootcamp = value.get(self.entity_description.key)
        return bootcamp if isinstance(bootcamp, bool) else None
