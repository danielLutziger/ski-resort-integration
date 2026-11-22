"""Data update coordinator for the Ski Resort Recommender."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_HOME_STATION, DOMAIN, LOGGER, UPDATE_INTERVAL
from .lib.errors import SkiApiError
from .lib.pipeline import TravelCache, build_recommendations
from .lib.resorts import load_resorts
from .lib.service import RecommendationResult
from .lib.settings import Settings

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .lib.models import Resort

RESORTS_DIR = Path(__file__).parent / "resorts"  # one <key>.yaml per resort

type SkiResortConfigEntry = ConfigEntry[SkiResortCoordinator]


class SkiResortCoordinator(DataUpdateCoordinator[RecommendationResult]):
    """Fetch forecasts and train connections, rank the ski days."""

    config_entry: SkiResortConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SkiResortConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._resorts: list[Resort] | None = None
        self._travel = TravelCache()  # SBB travel times, refreshed once a day

    @property
    def settings(self) -> Settings:
        """Settings from the config entry options (config flow follows later)."""
        home_station = self.config_entry.options.get(CONF_HOME_STATION)
        return Settings(home_station=home_station or None)

    async def _async_update_data(self) -> RecommendationResult:
        """Run one update; API problems become UpdateFailed."""
        if self._resorts is None:  # file I/O: not in the event loop
            self._resorts = await self.hass.async_add_executor_job(
                load_resorts, RESORTS_DIR
            )
        try:
            return await build_recommendations(
                async_get_clientsession(self.hass),
                self._resorts,
                self.settings,
                today=dt_util.now().date(),  # local date, not UTC
                cache=self._travel,
            )
        except SkiApiError as error:
            msg = f"Forecast update failed: {error}"
            raise UpdateFailed(msg) from error
