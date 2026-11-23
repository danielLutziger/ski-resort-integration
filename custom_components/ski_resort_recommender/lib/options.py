"""Config entry options (plain form values) <-> Settings, and their checks."""

from dataclasses import replace
from datetime import time, timedelta
from typing import TYPE_CHECKING, Any

from custom_components.ski_resort_recommender.lib.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Mapping

# option keys (also used in the Home Assistant form and translations)
HOME_STATION = "home_station"
WEEKDAYS = "weekdays"
MAX_RESULTS = "max_results"
MIN_GOOD_SCORE = "min_good_score"
ARRIVAL_EARLIEST = "arrival_earliest"
ARRIVAL_TARGET = "arrival_target"
ARRIVAL_LATEST = "arrival_latest"
WEATHER_INTERVAL_HOURS = "weather_interval_hours"
SHOW_OUTLOOK = "show_outlook"


def settings_from_options(options: Mapping[str, Any]) -> Settings:
    """Build Settings from the stored options; missing values keep the default."""
    settings = Settings()
    home_station = str(options.get(HOME_STATION, "")).strip() or None
    values: dict[str, Any] = {"home_station": home_station}
    if WEEKDAYS in options:
        values["allowed_weekdays"] = frozenset(int(d) for d in options[WEEKDAYS])
    if MAX_RESULTS in options:
        values["max_results"] = int(options[MAX_RESULTS])
    if SHOW_OUTLOOK in options:
        values["show_outlook"] = bool(options[SHOW_OUTLOOK])
    if MIN_GOOD_SCORE in options:
        values["min_good_score"] = float(options[MIN_GOOD_SCORE])
    for key in (ARRIVAL_EARLIEST, ARRIVAL_TARGET, ARRIVAL_LATEST):
        if key in options:
            values[key] = time.fromisoformat(options[key])
    if WEATHER_INTERVAL_HOURS in options:  # at least 1 h (Open-Meteo budget)
        hours = max(1, int(options[WEATHER_INTERVAL_HOURS]))
        values["weather_interval"] = timedelta(hours=hours)
    return replace(settings, **values)


def options_from_settings(settings: Settings) -> dict[str, Any]:
    """Form values for Settings (pre-fills the form with the defaults)."""
    return {
        HOME_STATION: settings.home_station or "",
        WEEKDAYS: [str(d) for d in sorted(settings.allowed_weekdays)],
        MAX_RESULTS: settings.max_results,
        MIN_GOOD_SCORE: settings.min_good_score,
        SHOW_OUTLOOK: settings.show_outlook,
        ARRIVAL_EARLIEST: settings.arrival_earliest.isoformat(),
        ARRIVAL_TARGET: settings.arrival_target.isoformat(),
        ARRIVAL_LATEST: settings.arrival_latest.isoformat(),
        WEATHER_INTERVAL_HOURS: settings.weather_interval // timedelta(hours=1),
    }


def validate_options(options: Mapping[str, Any]) -> dict[str, str]:
    """Return form errors (field -> translation key); empty when valid."""
    errors = {}
    if not options.get(WEEKDAYS):
        errors[WEEKDAYS] = "no_weekday"
    settings = settings_from_options(options)
    if not (
        settings.arrival_earliest <= settings.arrival_target <= settings.arrival_latest
    ):
        errors[ARRIVAL_TARGET] = "arrival_window"
    return errors
