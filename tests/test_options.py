"""Tests for the config entry options <-> Settings conversion and checks."""

from datetime import time, timedelta

from custom_components.ski_resort_recommender.lib.options import (
    ARRIVAL_EARLIEST,
    ARRIVAL_LATEST,
    ARRIVAL_TARGET,
    HOME_STATION,
    MAX_RESULTS,
    MIN_GOOD_SCORE,
    SHOW_OUTLOOK,
    TRAVEL_MODES,
    WEATHER_INTERVAL_HOURS,
    WEEKDAYS,
    options_from_settings,
    settings_from_options,
    validate_options,
)
from custom_components.ski_resort_recommender.lib.settings import CAR, TRAIN, Settings

FORM = {  # what the Home Assistant form returns (strings, floats)
    HOME_STATION: "Zürich HB",
    WEEKDAYS: ["4", "5", "6"],
    MAX_RESULTS: 4.0,
    MIN_GOOD_SCORE: 65.0,
    ARRIVAL_EARLIEST: "08:30:00",
    ARRIVAL_TARGET: "09:00:00",
    ARRIVAL_LATEST: "09:45:00",
    WEATHER_INTERVAL_HOURS: 6.0,
    SHOW_OUTLOOK: True,
}


def test_no_options_give_the_default_settings() -> None:
    """A fresh entry (no options yet) behaves like Settings()."""
    assert settings_from_options({}) == Settings()


def test_form_values_become_settings() -> None:
    """Strings and floats from the form are converted to the Settings types."""
    settings = settings_from_options(FORM)

    assert settings.home_station == "Zürich HB"
    assert settings.allowed_weekdays == frozenset({4, 5, 6})
    assert settings.max_results == 4
    assert settings.min_good_score == 65
    assert (settings.arrival_earliest, settings.arrival_target) == (
        time(8, 30),
        time(9, 0),
    )
    assert settings.arrival_latest == time(9, 45)
    assert settings.weather_interval == timedelta(hours=6)
    assert settings.show_outlook is True


def test_empty_home_station_means_no_trains() -> None:
    """A cleared text field (missing or blank) switches the SBB part off."""
    assert settings_from_options({HOME_STATION: "  "}).home_station is None
    assert settings_from_options({WEEKDAYS: ["5"]}).home_station is None


def test_defaults_round_trip_through_the_form() -> None:
    """The form is pre-filled from Settings() and gives Settings() back."""
    assert settings_from_options(options_from_settings(Settings())) == Settings()


def test_weather_interval_is_at_least_one_hour() -> None:
    """Protect the Open-Meteo budget from a 0 h interval."""
    assert settings_from_options(
        {WEATHER_INTERVAL_HOURS: 0}
    ).weather_interval == timedelta(hours=1)


def test_valid_form_has_no_errors() -> None:
    """The example form passes the checks."""
    assert validate_options(FORM) == {}


def test_arrival_window_must_be_in_order() -> None:
    """Earliest <= target <= latest."""
    wrong = {**FORM, ARRIVAL_TARGET: "10:00:00"}

    assert validate_options(wrong) == {ARRIVAL_TARGET: "arrival_window"}


def test_at_least_one_weekday() -> None:
    """Without a weekday nothing could ever be recommended."""
    assert validate_options({**FORM, WEEKDAYS: []}) == {WEEKDAYS: "no_weekday"}


def test_travel_modes_round_trip_and_unknown_modes_are_dropped() -> None:
    """Train and/or car; the form pre-fills train first."""
    both = settings_from_options({TRAVEL_MODES: ["car", "train", "plane"]})

    assert both.travel_modes == frozenset({TRAIN, CAR})
    assert options_from_settings(both)[TRAVEL_MODES] == ["train", "car"]
    assert settings_from_options({TRAVEL_MODES: []}).travel_modes == frozenset()
