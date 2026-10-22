"""Manual actions for BlockFront data collection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PLAYER_UUID, CONF_USERNAME, DOMAIN, MIN_INTERVALS, UPDATE_INTERVALS
from .coordinator import BlockFrontConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: BlockFrontConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the serialized refresh action."""
    async_add_entities([BlockFrontRefreshButton(entry)])


class BlockFrontRefreshButton(ButtonEntity):
    """Refresh every dataset one coordinator at a time."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_all"
    _attr_icon = "mdi:refresh"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_PLAYER_UUID]}_refresh_all"
        self._in_progress = False
        self._completed = 0
        self._last_error: str | None = None
        self._last_finished: str | None = None
        self._deferred: list[str] = []
        self._results: dict[str, str] = {}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.data[CONF_PLAYER_UUID])},
            name=self._entry.data[CONF_USERNAME],
            manufacturer="BlockFront",
            model="Player statistics",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "refresh_in_progress": self._in_progress,
            "datasets_completed": self._completed,
            "last_error": self._last_error,
            "last_finished": self._last_finished,
            "deferred_datasets": self._deferred,
            "dataset_results": self._results,
        }

    async def async_press(self) -> None:
        """Queue refreshes sequentially, coalescing repeated button presses."""
        if self._in_progress:
            return
        self._in_progress = True
        self._completed = 0
        self._last_error = None
        self._deferred = []
        self._results = {}
        self.async_write_ha_state()
        runtime = self._entry.runtime_data
        try:
            refresh_order = (
                "profile",
                "matches",
                "status",
                "online",
                "analytics",
                "history",
                "global",
                "archive",
            )
            for name in refresh_order:
                coordinator = runtime.coordinators[name]
                last_attempt = coordinator.last_attempt_at
                minimum = MIN_INTERVALS[UPDATE_INTERVALS[name]]
                if (
                    last_attempt is not None
                    and (datetime.now(UTC) - last_attempt).total_seconds() < minimum
                ):
                    self._deferred.append(name)
                    self._results[name] = "deferred_minimum_interval"
                    self._completed += 1
                    self.async_write_ha_state()
                    continue
                try:
                    await coordinator.async_refresh()
                except Exception as err:  # noqa: BLE001 - report per-dataset failure and continue
                    self._last_error = f"{coordinator.name}: {err}"
                    self._results[name] = "failed"
                else:
                    data = coordinator.data or {}
                    self._results[name] = "failed" if data.get("last_error") else "refreshed"
                self._completed += 1
                self.async_write_ha_state()
        finally:
            self._last_finished = datetime.now(UTC).isoformat()
            self._in_progress = False
            self.async_write_ha_state()
