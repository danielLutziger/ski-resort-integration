"""Sensor that shows the ski recommendation headline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME
from .coordinator import SkiResortConfigEntry, SkiResortCoordinator
from .lib.view import entry, sensor_state, sensor_table

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SkiResortConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the recommendation sensor."""
    async_add_entities([RecommendationSensor(entry.runtime_data)])


class RecommendationSensor(CoordinatorEntity[SkiResortCoordinator], SensorEntity):
    """State = headline; attributes = the recommendations and a Markdown table."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None  # the entity takes the device name
    _attr_icon = "mdi:ski"
    # large and changing every update: keep them out of the recorder database
    _unrecorded_attributes = frozenset({"recommendations", "outlook", "table"})

    def __init__(self, coordinator: SkiResortCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = entry_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name=NAME)

    @property
    def available(self) -> bool:
        """Stay available so the reason of a failed update stays visible."""
        return True

    @property
    def native_value(self) -> str:
        """Return the headline, or "No data yet" before the first good update."""
        return sensor_state(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Recommendations, outlook, the Markdown table and the last error."""
        result = self.coordinator.data
        error = None
        if not self.coordinator.last_update_success:
            error = str(self.coordinator.last_exception)
        return {
            "recommendations": [entry(r) for r in result.recommendations]
            if result
            else [],
            "outlook": entry(result.outlook, outlook=True)
            if result and result.outlook
            else None,
            "table": sensor_table(result, error),
            "last_error": error,
        }
