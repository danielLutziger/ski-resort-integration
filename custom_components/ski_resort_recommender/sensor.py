"""Sensor that shows the ski recommendation headline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, NAME
from .coordinator import SkiResortConfigEntry, SkiResortCoordinator

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
    """State = headline, attributes = recommendations (filled in step 5)."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_name = None  # the entity takes the device name
    _attr_icon = "mdi:ski"

    def __init__(self, coordinator: SkiResortCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = entry_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name=NAME)

    @property
    def native_value(self) -> str | None:
        """Return the headline (None until the coordinator delivers data)."""
        return None
