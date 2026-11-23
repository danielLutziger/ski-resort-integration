"""Data update coordinator for the Ski Resort Recommender."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER, UPDATE_INTERVAL
from .lib.errors import SkiApiError
from .lib.options import settings_from_options
from .lib.pipeline import Cache, build_recommendations
from .lib.resorts import load_resorts
from .lib.service import RecommendationResult

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .lib.models import Resort
    from .lib.settings import Settings

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
        # forecasts (weather interval) and SBB travel times (daily)
        self._cache = Cache()

    @property
    def settings(self) -> Settings:
        """Settings from the options form (defaults until it is saved once)."""
        # the car trip starts at HA's home, rounded to about 100 m for OSRM
        home = (
            round(self.hass.config.latitude, 3),
            round(self.hass.config.longitude, 3),
        )
        return replace(
            settings_from_options(self.config_entry.options), home_location=home
        )

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
                now=dt_util.now(),  # local time: today is the local date
                cache=self._cache,
            )
        except SkiApiError as error:
            minutes = int(UPDATE_INTERVAL.total_seconds() // 60)
            msg = f"{error} (next try in {minutes} min)"
            raise UpdateFailed(msg) from error
