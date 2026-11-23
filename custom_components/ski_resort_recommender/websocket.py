"""Websocket command for the card's modal: all results with their details."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import DOMAIN
from .lib.view import NO_DATA, results_payload, scoring_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import SkiResortCoordinator

RESULTS = f"{DOMAIN}/results"


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket command (once, in async_setup)."""
    websocket_api.async_register_command(hass, ws_results)


@websocket_api.websocket_command({vol.Required("type"): RESULTS})
@callback
def ws_results(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send every result (all resort-days) with details and the scoring info."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    coordinator: SkiResortCoordinator = entries[0].runtime_data
    error = None
    if not coordinator.last_update_success:
        error = str(coordinator.last_exception)
    if coordinator.data is None:
        connection.send_result(
            msg["id"],
            {
                "headline": NO_DATA,
                "last_error": error,
                "results": [],
                "scoring": scoring_info(coordinator.settings),
            },
        )
        return
    connection.send_result(
        msg["id"], results_payload(coordinator.data, coordinator.settings, error)
    )
