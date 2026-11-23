"""Config flow (add the integration) and options flow (settings form)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, NAME
from .lib.errors import SkiApiError
from .lib.options import (
    ARRIVAL_EARLIEST,
    ARRIVAL_LATEST,
    ARRIVAL_TARGET,
    HOME_STATION,
    MAX_RESULTS,
    MIN_GOOD_SCORE,
    SHOW_OUTLOOK,
    WEATHER_INTERVAL_HOURS,
    WEEKDAYS,
    options_from_settings,
    validate_options,
)
from .lib.sbb import find_stations
from .lib.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Mapping

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
WEEKDAY_NAMES += ("Saturday", "Sunday")
MAX_SUGGESTIONS = 5


def _number(low: float, high: float, step: float, unit: str | None = None) -> Any:
    """Build a number box for the form (unit only when there is one)."""
    config = selector.NumberSelectorConfig(
        min=low, max=high, step=step, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(HOME_STATION): selector.TextSelector(),
        vol.Required(WEEKDAYS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=str(i), label=name)
                    for i, name in enumerate(WEEKDAY_NAMES)
                ],
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Required(MAX_RESULTS): _number(1, 5, 1),
        vol.Required(SHOW_OUTLOOK): selector.BooleanSelector(),
        vol.Required(MIN_GOOD_SCORE): _number(0, 100, 1, "points"),
        vol.Required(ARRIVAL_EARLIEST): selector.TimeSelector(),
        vol.Required(ARRIVAL_TARGET): selector.TimeSelector(),
        vol.Required(ARRIVAL_LATEST): selector.TimeSelector(),
        vol.Required(WEATHER_INTERVAL_HOURS): _number(1, 12, 1, "h"),
    }
)


class SkiResortConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the integration without any input; settings are in the options."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a confirm step, then create the entry."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=NAME, data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SkiResortOptionsFlow:  # noqa: ARG004
        """Return the settings form (the Configure button)."""
        return SkiResortOptionsFlow()


class SkiResortOptionsFlow(OptionsFlowWithReload):
    """Settings form; saving reloads the integration with the new values."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the form; check the values and the home station."""
        errors: dict[str, str] = {}
        placeholders = {"suggestions": "-"}
        if user_input is not None:
            errors = validate_options(user_input)
            station = str(user_input.get(HOME_STATION, "")).strip()
            if station and not errors:
                errors, found = await self._check_station(station, placeholders)
                if found:
                    user_input[HOME_STATION] = found  # the timetable's spelling
            if not errors:
                return self.async_create_entry(data=user_input)

        values: Mapping[str, Any] = {
            **options_from_settings(Settings()),
            **self.config_entry.options,
            **(user_input or {}),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, values),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _check_station(
        self, station: str, placeholders: dict[str, str]
    ) -> tuple[dict[str, str], str | None]:
        """Find the station in the SBB timetable; suggest names if it isn't exact."""
        try:
            names = await find_stations(async_get_clientsession(self.hass), station)
        except SkiApiError:
            return {"base": "cannot_connect"}, None
        exact = next((n for n in names if n.casefold() == station.casefold()), None)
        if exact:
            return {}, exact
        placeholders["suggestions"] = ", ".join(names[:MAX_SUGGESTIONS]) or "-"
        return {HOME_STATION: "station_not_found"}, None
