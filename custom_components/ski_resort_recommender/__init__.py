"""The Ski Resort Recommender integration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

from . import websocket
from .const import DOMAIN, LOGGER
from .coordinator import SkiResortConfigEntry, SkiResortCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)  # no YAML configuration
CARD_FILE = Path(__file__).parent / "frontend" / "ski-resort-card.js"
CARD_URL = f"/{DOMAIN}/ski-resort-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001
    """Register what exists once per Home Assistant (not per entry)."""
    websocket.async_register(hass)
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it in every browser (custom:ski-resort-card)."""
    if getattr(hass, "http", None) is None:  # e.g. a test core without web server
        LOGGER.debug("No HTTP server: dashboard card not registered")
        return
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")  # new version = no stale cache


async def async_setup_entry(hass: HomeAssistant, entry: SkiResortConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    coordinator = SkiResortCoordinator(hass, entry)
    # no first_refresh: a failing first update (e.g. Open-Meteo 429) must not stop
    # the setup, the sensor shows the reason and the coordinator retries hourly
    await coordinator.async_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SkiResortConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
