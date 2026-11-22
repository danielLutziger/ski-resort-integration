"""Sensor that shows the ski recommendation headline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME
from .coordinator import SkiResortConfigEntry, SkiResortCoordinator
from .lib.view import entry, headline, render_table

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
    def native_value(self) -> str | None:
        """Return the headline: Good day / No good day / No forecast yet."""
        if self.coordinator.data is None:
            return None
        return headline(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Recommendations (top results + outlook) and the Markdown table."""
        result = self.coordinator.data
        if result is None:
            return None
        return {
            "recommendations": [entry(r) for r in result.recommendations],
            "outlook": entry(result.outlook, outlook=True) if result.outlook else None,
            "table": render_table(result),
        }
