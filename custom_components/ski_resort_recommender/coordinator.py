"""Data update coordinator for the Ski Resort Recommender."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type SkiResortConfigEntry = ConfigEntry[SkiResortCoordinator]


class SkiResortCoordinator(DataUpdateCoordinator[None]):
    """Fetch forecasts once per hour and compute the recommendations."""

    # Stub for now: fetching and scoring are wired in later (CLAUDE.md, step 5).

    config_entry: SkiResortConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SkiResortConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
        )

    async def _async_update_data(self) -> None:
        """Return no data until the forecast provider is wired in."""
        return
