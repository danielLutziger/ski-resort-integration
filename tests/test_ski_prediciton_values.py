"""Tests for score_day()."""

from datetime import date

from custom_components.ski_resort_recommender.lib.models import DayForecast
from custom_components.ski_resort_recommender.lib.scoring import score_day


def test_sunny_cold_day_beats_rainy_day() -> None:
    """A clear day scores higher than a rainy one."""
    sunny = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=0,
        vision=None,
    )

    rainy = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=63,
        vision=None,
    )

    assert score_day(sunny).total > score_day(rainy).total


def test_good_vision_cloudy_beats_bad_vision_cloudy() -> None:
    """Placeholder for visibility: for now compares weather codes."""
    sunny = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=0,
        vision=None,
    )

    rainy = DayForecast(
        day=date(2026, 12, 5),
        temp_min_c=-8,
        temp_max_c=2,
        snowfall_cm=0,
        sunshine_hours=8,
        wind_max_kmh=10,
        weather_code=63,
        vision=None,
    )

    assert score_day(sunny).total > score_day(rainy).total


# test cases:
# bad weather good vision > good weather bad vision
# good vision snow > medium vision
# good vision bad weather > high wind speed + slush
# Only the allowed weekdays appear, and a perfect Wednesday is excluded.
# The same resort can appear twice, on different days.
# Max 3 results, best first.
# A rainy weekend returns results where has_good_day is False.
# A resort missing from forecasts doesn't crash.
